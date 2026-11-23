#Library that enables the API
#Use the requests library to make a GET request to the API endpoint
import requests

#time bruges til time.sleep(), en funktion der tillader at holde pause mellem to linjer kode. Det skal man, fordi en API ikke
# har godt af at blive bombarderet med requests. Derfor er det en god idé at holde pause mellem to requests, så 
# man ikke bliver blokeret.
import time

import os
from dotenv import load_dotenv

#STEAM_API_KEY is used to call the informotion of user data from steams API and is a string variable.
# It is loaded from the .env file (see .env.example) so the key is never committed to git.
load_dotenv()
STEAM_API_KEY = os.environ["STEAM_API_KEY"]
#Steam official API endpoint
api = "https://api.steampowered.com"

#Requests.get henter data fra api
response = requests.get(api)

### Claude Code block der henter api data fra steam
def get(interface, method, version, **params):
    #url definerer endpointet til API'et. Interface er hvilken del af steam man arbejder med
    url = f"{api}/{interface}/{method}/{version}/" 
    params["key"] = STEAM_API_KEY
    # response er den "pakke" der indholder alt det hentet api data fra et given api kald
    response = requests.get(url, params=params)
    response.raise_for_status()   # fejl hvis status ikke er 200
    return response.json()        # svaret som Python-dict

#  Venneliste for en bruger
#   GetFriendlist is -> method <- from URL which fetches the friendlist from the user.
#   steamid is the unique identifier for the user whose friend list is being fetched. Has to be the numeric steamid of the user.
#   Friends_since 
# {'friendslist': {'friends': 
# [{'steamid': '76561197964327488', 
# 'relationship': 'friend', 
# 'friend_since': 1728676250} -> unix timestamp format <- shows the senconds they have been friends with the user in seconds.

friends = get("ISteamUser", "GetFriendList", "v1",
              steamid="76561198085894149", relationship="friend")

# Spillebibliotek for en bruger. GetOwnedGames er spil man ejer, og include_appinfo=1 betyder at vi også får spillets navn med. include_played_free_games=1 betyder at vi også får gratis spil med (fx Smite).
games = get("IPlayerService", "GetOwnedGames", "v1",
            steamid="76561198085894149", include_appinfo=1,
            include_played_free_games=1)   # tag også gratis spil (fx Smite) med

# Profiloplysninger (navn, avatar osv.)
profile = get("ISteamUser", "GetPlayerSummaries", "v2",
              steamids="76561198085894149")


# Claude code skrevet funktion til at hente appid fra steamspy
# steamspy er en tredjeparts API, der giver information om spil på Steam. Den kan bruges til at hente oplysninger om spil, herunder tags, anmeldelser og statistik.
# appid is the unique identifier for the game in steamspy. It is a numeric value that can be used to fetch information about the game.
def fetch_tags(appid):
    url = "https://steamspy.com/api.php"
    reply = requests.get(url, params={"request": "appdetails", "appid": appid}, timeout=20)
    reply.raise_for_status()
    data = reply.json()
    return data["tags"] 

# The merged and excluded tags now live in tag_rules.py, so they can be edited while the server runs.
# importlib.reload() reads the file again, so we always get the newest version of the rules.
import importlib
import tag_rules

def load_rules():
    importlib.reload(tag_rules)
    return tag_rules.merged_tags, tag_rules.excluded_tags

# Cache for tags we have already fetched, so we never fetch the same game twice.
# The cache is saved in a file (tag_cache.json), so it is also remembered the next time we run the program.
import json
import os

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tag_cache.json")

# Load the cache from the file if it exists, otherwise start with an empty one.
# Note: JSON only allows text as keys, so the appid is stored as a string ("730", not 730).
import threading

tag_cache = {}
cache_loaded_time = 0        # when tag_cache.json was last changed, the last time we read it

# In the server, two things use tag_cache at the same time: the background tag fetcher (adds tags)
# and p5's network requests (read tags). The lock makes them take turns, so one never sees
# the cache half-changed. "with cache_lock:" = wait until nobody else is using the cache.
cache_lock = threading.RLock()

# Reads tag_cache.json again, but only if the file has changed since we last read it.
# Needed because the server keeps running while e.g. refresh_games() (another program) adds tags to the file.
def reload_cache_if_changed():
    global cache_loaded_time
    with cache_lock:
        if not os.path.exists(CACHE_FILE):
            return
        changed_time = os.path.getmtime(CACHE_FILE)
        if changed_time != cache_loaded_time:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                new_cache = json.load(f)
            tag_cache.clear()
            tag_cache.update(new_cache)
            cache_loaded_time = changed_time

reload_cache_if_changed()    # load the cache when the program starts


# Saves the cache to the file. We call it every time we fetch a new game,
# so nothing is lost if the program is stopped halfway through.
# Like network.json, we write to a temporary file first, so nobody ever reads a half-written cache.
def save_cache():
    global cache_loaded_time
    with cache_lock:
        temp_file = CACHE_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(tag_cache, f, indent=2)
        os.replace(temp_file, CACHE_FILE)
        cache_loaded_time = os.path.getmtime(CACHE_FILE)   # we wrote it ourselves, no need to read it again


# We need to associate games with genres. We do this through a game's top 5 tags, where the game
# is added to each of its tags (genres). The purpose is to be able to look up a specific genre
# per player and see how many hours they have in that genre (per tag).
#
# This is split into two steps:
#   fetch_player_games(): asks Steam for a player's games (slow: uses the internet)
#   genres_from_games(): sorts those games into genres using tag_rules.py (fast: no internet)
# network.json stores the games, so the genres can be worked out again whenever the rules change.

# Games played less than this many hours are left out of the library (and we don't fetch their tags).
# This keeps scans faster and ignores games someone just tried once.
LIBRARY_MIN_HOURS = 10


# Makes sure a game's tags are in the tag cache. Only asks SteamSpy if we don't have them yet.
def ensure_tags(appid):
    key = str(appid)                          # the cache file stores appids as text
    if key in tag_cache:
        return
    try:
        tags = fetch_tags(appid)              # all tags: {"FPS": 90000, "Shooter": 65000, ...}
    except (requests.exceptions.RequestException, ValueError, KeyError):
        # SteamSpy failed (timeout, error, strange answer). Skip the game for now:
        # we don't save anything, so it is tried again next time.
        print("Could not fetch tags for", appid)
        time.sleep(1)
        return
    with cache_lock:
        tag_cache[key] = tags
        save_cache()                          # save to file straight away
    time.sleep(1)                             # wait 1 second so SteamSpy doesn't block us


# ---- Background tag fetching (used by server.py) ----
# Without it, a scan waits ~1 second per new game before it can add the next friend.
# With it, the scan only puts new games in a queue and moves on; a background thread fetches
# their tags one per second (SteamSpy's limit) while p5 colours the dots in as the tags arrive.
import queue

tag_queue = queue.Queue()     # games waiting for tags (first in, first out)
queued_appids = set()         # the same games, so we don't put a game in the queue twice
background_tags = False       # True once start_tag_worker() has been called (only in server.py)


# Puts a game in the queue, unless we already have its tags or it's already waiting.
def queue_tags(appid):
    key = str(appid)
    if key in tag_cache or key in queued_appids:
        return
    queued_appids.add(key)
    tag_queue.put(appid)


# How many games are still waiting for tags (p5 shows this).
def tags_waiting():
    return len(queued_appids)


# The background thread: takes games from the queue one at a time and fetches their tags.
def tag_worker():
    while True:
        appid = tag_queue.get()               # waits here until there is a game in the queue
        ensure_tags(appid)                    # fetch the tags (and wait 1 second)
        queued_appids.discard(str(appid))


# Starts the background thread. daemon=True: the thread stops when the server stops.
def start_tag_worker():
    global background_tags
    background_tags = True
    threading.Thread(target=tag_worker, daemon=True).start()


# Fetches a player's games from Steam, and makes sure their tags are in the tag cache.
# steam_id: the player's numeric Steam ID. count: how many of the most played games go in "games".
# Returns a dictionary with two lists of games, each game like {"appid": 730, "name": "Counter-Strike 2", "hours": 1341.7}:
#   "games":   the player's `count` most played games (used by compare)
#   "library": every game played at least LIBRARY_MIN_HOURS hours (used for the colour in p5)
# Returns None if the profile is private.
def fetch_player_games(steam_id, count=10):
    # game_data is what we get back from the Steam API. "response" contains "games", which is a list
    # with information about the games the user owns.
    game_data = get("IPlayerService", "GetOwnedGames", "v1",
                    steamid=steam_id, include_appinfo=1,
                    include_played_free_games=1)   # also include free games (e.g. Smite)

    # If the profile is private, there is no "games" in the response
    game_list = game_data["response"].get("games", [])
    if not game_list:
        print("No games found for", steam_id, "(is the profile private?)")
        return None

    # Sort all games by playtime (most minutes first), so the most played games come first
    most_played = sorted(game_list, key=lambda game: game["playtime_forever"], reverse=True)

    # Turn Steam's game info into our own small format
    all_games = [{
        "appid": game["appid"],
        "name": game["name"],
        # playtime_forever (Steam API) is playtime in MINUTES, so we divide by 60 to get hours
        "hours": round(game["playtime_forever"] / 60, 1),
    } for game in most_played]

    top_games = all_games[:count]
    library = [game for game in all_games if game["hours"] >= LIBRARY_MIN_HOURS]

    # Tags for every game we will use (top games + library).
    # In the server they go in the background queue; otherwise (e.g. python fetch.py) we fetch them now.
    for game in top_games + library:
        if background_tags:
            queue_tags(game["appid"])
        else:
            ensure_tags(game["appid"])

    return {"games": top_games, "library": library}


# Only the most played games (as before). Returns an empty list if the profile is private.
def fetch_top_games(steam_id, count=10):
    player_games = fetch_player_games(steam_id, count)
    return player_games["games"] if player_games else []


# Sorts a list of games (from fetch_top_games) into genres, using the rules in tag_rules.py.
#
# VOTE WEIGHTING: each game is worth 1 point, split over its top 5 tags by how many votes each tag has.
# Example: a shooter with Shooter 900 votes, Military 100 votes -> Shooter gets 0.9, Military 0.1.
# So a weak "side tag" (like Co-op or Military on a shooter) counts much less than the game's main genre.
# The game's hours are split the same way.
#
# Returns a dictionary: {"RPG": {"hours": 800.5, "count": 3.4, "games": ["Skyrim", "Fallout 4"]}, ...}
#   hours: hours in the genre (weighted)   count: number of games in the genre (weighted)
#   games: names of all games that have the genre among their top 5 tags
def genres_from_games(games):
    merged_tags, excluded_tags = load_rules()     # newest version of tag_rules.py

    # Empty dictionary where we collect the genres for this player
    genres = {}

    for game in games:
        name = game["name"]
        hours = game["hours"]
        tags = tag_cache.get(str(game["appid"]), {})

        if tags:                                  # if the game has tags (otherwise it is an empty list)
            # First remove the excluded tags, so the top 5 are the 5 best REMAINING tags
            tags = {tag: votes for tag, votes in tags.items() if tag not in excluded_tags}
            # Combine tags that mean the same thing and add their votes together
            combined = {}
            for tag, votes in tags.items():
                new_name = merged_tags.get(tag, tag)   # use the new name if there is one, otherwise the tag itself
                combined[new_name] = combined.get(new_name, 0) + votes
            # Remove excluded tags AGAIN after merging: e.g. "FPS" is merged into "Shooter",
            # so if "Shooter" is excluded, it would otherwise come back here.
            combined = {tag: votes for tag, votes in combined.items() if tag not in excluded_tags}
            # Sort by number of votes (highest first) and keep only the 5 most popular tags
            top5 = sorted(combined, key=combined.get, reverse=True)[:5]
        else:
            top5 = []

        # Add the game to each of its 5 tags (genres), weighted by the tag's share of the votes
        top5_votes = sum(combined[tag] for tag in top5) if top5 else 0
        for tag in top5:
            # this tag's part of the game's 1 point (0 to 1). If there are no votes at all, split equally.
            weight = combined[tag] / top5_votes if top5_votes else 1 / len(top5)
            if tag not in genres:                         # first time we see the tag: create it
                genres[tag] = {"hours": 0, "count": 0, "games": []}
            genres[tag]["hours"] += hours * weight        # add the tag's part of the game's hours
            genres[tag]["count"] += weight                # add the tag's part of the game
            genres[tag]["games"].append(name)              # add the game's name to the genre's list of games

    return genres


# Both steps in one: fetch a player's games and sort them into genres (used by compare etc.)
def fetch_genres(steam_id, count=10):
    return genres_from_games(fetch_top_games(steam_id, count))


# How big a part of a player's library each genre is, counted in games.
# Example: 10 games in the library, and RPG's (vote weighted) count is 4 -> {"RPG": 0.4, ...}
def genre_shares(genres, library_size):
    return {tag: genres[tag]["count"] / library_size for tag in genres}


# The genre we colour a player by: the genre the player has MORE of than the average player in the network.
# If everybody plays shooters, being a shooter player doesn't stand out, so another genre can win.
#   1) Sort the player's genres by hours and take the top 10 (so the colour is a genre they really play).
#   2) For each of those 10: the player's share of games in the genre MINUS the network's average share.
#   3) The genre where the player is furthest above average wins.
# genres: the player's genres (from genres_from_games). library_size: number of games in their library.
# average_shares: the average share per genre over all players (see network_with_genres).
# Returns None if the player has no genres.
def standout_genre(genres, library_size, average_shares):
    if not genres:
        return None
    shares = genre_shares(genres, library_size)
    strength = tag_rules.STANDOUT_STRENGTH     # set in tag_rules.py (0 = most games wins, 1 = most above average wins)
    top10 = sorted(genres, key=lambda tag: genres[tag]["hours"], reverse=True)[:10]
    return max(top10, key=lambda tag: shares[tag] - strength * average_shares.get(tag, 0))


# Compares the genres of two players and prints the result.
def compare(name1, genres1, name2, genres2):
    # Total hours for each player (used to calculate percentages)
    total1 = sum(g["hours"] for g in genres1.values())
    total2 = sum(g["hours"] for g in genres2.values())

    # Genres that both players have (set & set = what they have in common)
    shared = set(genres1) & set(genres2)

    # Show the shared genres, sorted by how much both players play them (the smaller of the two hour counts)
    print("\nShared genres (sorted by how much both players play):")
    print(f"{'Genre':<25}{name1:>12}{name2:>12}")
    for tag in sorted(shared, key=lambda t: min(genres1[t]["hours"], genres2[t]["hours"]), reverse=True):
        print(f"{tag:<25}{genres1[tag]['hours']:>11.1f}t{genres2[tag]['hours']:>11.1f}t")

    # Similarity score: for each shared genre we take the smaller share of the player's playtime.
    # If both players spread their time identically the score is 100 %. No shared genres gives 0 %.
    similarity = sum(min(genres1[t]["hours"] / total1, genres2[t]["hours"] / total2) for t in shared)
    print(f"\nSimilarity between {name1} and {name2}: {round(similarity * 100)} %")
    return similarity          # give the score back so it can be used elsewhere


# Looks up a player's profile name (personaname), so we can show playername instead of a long number.
def get_name(steam_id):
    profile = get("ISteamUser", "GetPlayerSummaries", "v2", steamids=steam_id)
    players = profile["response"]["players"]
    if not players:                 # deleted or banned account: Steam returns no player
        return steam_id
    return players[0]["personaname"]


# Fetches a player's friend list and returns it as a set of Steam IDs.
# If the friend list is private, Steam answers with an error (401), and we return an empty set.
def get_friend_ids(steam_id):
    try:
        data = get("ISteamUser", "GetFriendList", "v1", steamid=steam_id, relationship="friend")
    except requests.exceptions.HTTPError:
        print("Friend list is private for", steam_id)
        return set()
    return {friend["steamid"] for friend in data["friendslist"]["friends"]}


### The network that p5.js draws (network.json) ###
# Nodes = players, with their most played genre (used for the colour in p5).
# Edges = a line between two players who are friends on Steam.
# Looks like: {"nodes": [{"id": ..., "name": ..., "top_genre": ...}], "edges": [{"source": ..., "target": ...}]}
#
# The network GROWS: we load the existing network.json, add players to it and save it again.

NETWORK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "network.json")

# How many of a player's friends we scan at most per scan. Every friend costs a few API calls
# (and SteamSpy needs 1 second per new game), so start small and raise it when it works.
MAX_FRIENDS = 100


# Loads network.json, or starts an empty network if the file doesn't exist yet.
def load_network():
    if os.path.exists(NETWORK_FILE):
        with open(NETWORK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"nodes": [], "edges": []}


# Saves the network as network.json, so the p5.js sketch can load it.
# We first write to a temporary file and then swap it in, so p5 never reads a half-written file.
def save_network(network):
    temp_file = NETWORK_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(network, f, indent=2, ensure_ascii=False)   # ensure_ascii=False keeps names like "Søren" readable
    os.replace(temp_file, NETWORK_FILE)
    print(f"Saved {len(network['nodes'])} players and {len(network['edges'])} connections")


# Adds a friendship line between a and b, unless it is already there (A-B and B-A count as the same).
def add_edge(network, a, b):
    for edge in network["edges"]:
        if {edge["source"], edge["target"]} == {a, b}:
            return
    network["edges"].append({"source": a, "target": b})


# Adds ONE player to the network and connects them to the friends already in the network.
# Players with a private game list are added too, just without games: they become grey dots in p5,
# but we still see who they are friends with.
# Returns True (the player is always in the network afterwards).
def add_player(network, steam_id):
    node_ids = {node["id"] for node in network["nodes"]}
    if steam_id in node_ids:            # already in the network: nothing to do
        return True

    player_games = fetch_player_games(steam_id)
    private = player_games is None      # private profile (or no games at all)
    if private:
        player_games = {"games": [], "library": []}

    # We save the player's games, not their genre. The genre is worked out by network_with_genres()
    # every time p5 loads the network, so it always follows the newest tag_rules.py.
    network["nodes"].append({
        "id": steam_id,
        "name": get_name(steam_id),
        "private": private,                   # True = Steam hides this player's games
        "games": player_games["games"],       # 10 most played games
        "library": player_games["library"],   # all games with at least LIBRARY_MIN_HOURS hours
    })

    # Connect the new player to every friend that is already in the network
    for friend_id in get_friend_ids(steam_id):
        if friend_id in node_ids:
            add_edge(network, steam_id, friend_id)

    save_network(network)               # save after every player, so p5 can show the network growing
    return True


# Scans a player: adds the player, then loops through their friend list and adds each friend.
# This is the first level of the friend-list search (x, then all of x's friends).
def scan(steam_id):
    network = load_network()
    print("Scanning", steam_id)

    if not add_player(network, steam_id):
        print("Cannot scan", steam_id, "(private profile?)")
        return network

    friend_ids = sorted(get_friend_ids(steam_id))[:MAX_FRIENDS]
    for number, friend_id in enumerate(friend_ids, start=1):
        print(f"Friend {number}/{len(friend_ids)}: {friend_id}")
        if add_player(network, friend_id):
            # We KNOW they are friends (friend_id came from steam_id's list), so we always add the line.
            # That way the line is there even if the friend's own friend list is private.
            add_edge(network, steam_id, friend_id)
            save_network(network)

    print("Scan done")
    return network


# Loads network.json and adds each player's top_genre, worked out with the newest tag_rules.py.
# server.py sends THIS to p5 (not the raw file), so editing tag_rules.py + refreshing the page is enough.
# top_genre is None (shown as grey in p5) for players who hide their playtime on Steam:
# all their games show 0 hours, so their library (games with LIBRARY_MIN_HOURS+ hours) is empty.
def network_with_genres():
    # Hold the cache lock the whole time, so the background tag fetcher can't change the cache halfway
    with cache_lock:
        network = calculate_genres()

    # We compare genres, so players without genre data are NOT sent to p5 (they stay in network.json).
    # That's private profiles, hidden playtime, and players whose games are still waiting for tags
    # (those appear as soon as their tags arrive).
    shown_ids = {node["id"] for node in network["nodes"] if node["top_genre"] is not None}
    network["nodes"] = [node for node in network["nodes"] if node["id"] in shown_ids]
    network["edges"] = [edge for edge in network["edges"]
                        if edge["source"] in shown_ids and edge["target"] in shown_ids]

    network["tags_waiting"] = tags_waiting()   # p5 keeps reloading while this is above 0
    return network


# Players whose games don't have tags yet (still in the background queue) get top_genre None
# until the tags arrive, so they are grey for a moment and then get their colour.
def calculate_genres():
    reload_cache_if_changed()   # pick up tags that another program has fetched in the meantime
    network = load_network()

    # 1) Every player's genres, from their library.
    #    Players saved before we had libraries (no "library" yet) use their 10 top games for now.
    for node in network["nodes"]:
        games = node["library"] if "library" in node else node.get("games", [])
        node["_genres"] = genres_from_games(games)
        node["_size"] = len(games)

    # 2) The network's average share per genre. Players without a genre count as 0 for it.
    players_with_data = [node for node in network["nodes"] if node["_genres"]]
    average_shares = {}
    for node in players_with_data:
        for tag, share in genre_shares(node["_genres"], node["_size"]).items():
            average_shares[tag] = average_shares.get(tag, 0) + share / len(players_with_data)

    # 3) Each player's colour: the genre where they are furthest above average
    for node in network["nodes"]:
        node["top_genre"] = standout_genre(node["_genres"], node["_size"], average_shares)
        del node["_genres"], node["_size"]     # only needed for the calculation, don't send to p5
    return network


# Fetches the games again for EVERY player already in network.json (e.g. to update their hours).
# Friendships are not changed. Asks Steam once per player, plus SteamSpy once (1 second) per new game,
# so the first time it can take a while.
# You do NOT need this after editing tag_rules.py - just refresh the page.
# Run it with:  .venv/bin/python -c "import fetch; fetch.refresh_games()"
# only_missing=True skips players who already have a library with the current LIBRARY_MIN_HOURS,
# e.g. to continue after the internet dropped:  fetch.refresh_games(only_missing=True)
def refresh_games(only_missing=False):
    network = load_network()
    for number, node in enumerate(network["nodes"], start=1):
        library = node.get("library")
        if only_missing and library and all(game["hours"] >= LIBRARY_MIN_HOURS for game in library):
            continue
        player_games = fetch_player_games(node["id"])
        if player_games:            # if the profile became private, keep the games we have
            node["games"] = player_games["games"]
            node["library"] = player_games["library"]
        node.pop("top_genre", None) # old networks saved top_genre in the file; it's worked out live now
        print(f"{number}/{len(network['nodes'])} {node['name']}: {len(node.get('library', []))} games in library")
        save_network(network)       # save after every player, so p5 can show the colours change
    return network


# ---- Run the program ----
# This part only runs when you start fetch.py yourself (python fetch.py),
# NOT when server.py uses the functions above.
if __name__ == "__main__":
    scan("76561198095791418")   # orb

# Look up a specific genre for a player, e.g. how many hours a player has in RPG:
# print(fetch_genres(players[0])["RPG"]["hours"])