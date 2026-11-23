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
    reply = requests.get(url, params={"request": "appdetails", "appid": appid})
    reply.raise_for_status()
    data = reply.json()
    return data["tags"] 

# Tags vi ekskluderer, fordi de beskriver HVORDAN man spiller (perspektiv, spiltilstand, pris osv.)
# og ikke hvad spillet handler om. Tilføj eller fjern tags her, efterhånden som I ser dem i outputtet.
excluded_tags = {
    "Free to Play", "Early Access", "Great Soundtrack", "Moddable",   # pris/status/ekstra
    "Third Person", "First-Person", "Isometric", "2D", "3D",          # kameraperspektiv
    "Singleplayer", "Multiplayer", "Co-op", "Online Co-Op",           # spiltilstand
    "Local Co-Op", "PvP", "PvE", "Team-Based", "Massively Multiplayer",
}

# Tags der betyder (næsten) det samme slås sammen til ét tag.
# Nøglen er tagget, vi finder hos SteamSpy, og værdien er det tag, vi vil bruge i stedet.
# Eksempel: "Turn-Based Combat" og "Turn-Based Strategy" bliver begge til "Turn-Based".
merged_tags = {
    "Turn-Based Combat": "Turn-Based", "Turn-Based Strategy": "Turn-Based",
    "Tactical RPG": "RPG", "Action RPG": "RPG", "CRPG": "RPG", "JRPG": "RPG", 
    "MMORPG":"MMO","Massively Multiplayer":"MMO",
    "FPS": "Shooter", "Third-Person Shooter": "Shooter", "Looter Shooter": "Shooter", "Hero Shooter": "Shooter",
    "Open World Survival Craft": "Survival",
    "Dark Fantasy": "Fantasy",
    "Space": "Sci-fi",
}

# Cache for tags we have already fetched, so we never fetch the same game twice.
# The cache is saved in a file (tag_cache.json), so it is also remembered the next time we run the program.
import json
import os

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tag_cache.json")

# Load the cache from the file if it exists, otherwise start with an empty one.
# Note: JSON only allows text as keys, so the appid is stored as a string ("730", not 730).
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        tag_cache = json.load(f)
else:
    tag_cache = {}


# Saves the cache to the file. We call it every time we fetch a new game,
# so nothing is lost if the program is stopped halfway through.
def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(tag_cache, f, indent=2)


# We need to associate games with genres. We do this through a game's top 5 tags, where the game
# is added to each of its tags (genres). The purpose is to be able to look up a specific genre
# per player and see how many hours they have in that genre (per tag).
#
# This function fetches a player's most played games and sorts them into genres (tags).
# steam_id: the player's numeric Steam ID. count: how many of the most played games to look at.
# Returns a dictionary: {"RPG": {"hours": 800.5, "games": ["Skyrim", "Fallout 4"]}, ...}
# Key = tag (genre), value = total hours in that genre and all games that have the tag.

def fetch_genres(steam_id, count=10):
    # game_data is what we get back from the Steam API. "response" contains "games", which is a list
    # with information about the games the user owns.
    game_data = get("IPlayerService", "GetOwnedGames", "v1",
                    steamid=steam_id, include_appinfo=1,
                    include_played_free_games=1)   # also include free games (e.g. Smite)

    # If the profile is private, there is no "games" in the response
    game_list = game_data["response"].get("games", [])
    if not game_list:
        print("No games found for", steam_id, "(is the profile private?)")
        return {}

    # Sort all games by playtime (most minutes first), so the most played games come first
    most_played = sorted(game_list, key=lambda game: game["playtime_forever"], reverse=True)

    # Empty dictionary where we collect the genres for this player
    genres = {}

    # Loop through the games and get the name, appid and tags of each game.
    # We take only the games with the most hours (the number is set by "count").
    for game in most_played[:count]:
        appid = game["appid"]
        name = game["name"]
        # playtime_forever (Steam API) is playtime in MINUTES, so we divide by 60 to get hours
        hours = round(game["playtime_forever"] / 60, 1)

        # Only fetch tags from SteamSpy if we don't already have them
        key = str(appid)                          # the cache file stores appids as text
        if key not in tag_cache:
            tag_cache[key] = fetch_tags(appid)    # all tags: {"FPS": 90000, "Shooter": 65000, ...}
            save_cache()                          # save to file straight away
            time.sleep(1)                         # wait 1 second so SteamSpy doesn't block us
        tags = tag_cache[key]

        if tags:                                  # if the game has tags (otherwise it is an empty list)
            # First remove the excluded tags, so the top 5 are the 5 best REMAINING tags
            tags = {tag: votes for tag, votes in tags.items() if tag not in excluded_tags}
            # Combine tags that mean the same thing and add their votes together
            combined = {}
            for tag, votes in tags.items():
                new_name = merged_tags.get(tag, tag)   # use the new name if there is one, otherwise the tag itself
                combined[new_name] = combined.get(new_name, 0) + votes
            # Sort by number of votes (highest first) and keep only the 5 most popular tags
            top5 = sorted(combined, key=combined.get, reverse=True)[:5]
        else:
            top5 = []

        # Add the game to each of its 5 tags (genres)
        for tag in top5:
            if tag not in genres:                         # first time we see the tag: create it
                genres[tag] = {"hours": 0, "games": []}
            genres[tag]["hours"] += hours                 # add the game's hours to the genre's total hours
            genres[tag]["games"].append(name)              # add the game's name to the genre's list of games

    return genres


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


# ---- Run the program ----
# Change player2 to another player's numeric Steam ID (the profile must be public)
player1 = "76561198095791418"                                  # orb
player2 = "76561198009014566"                                   #oliver
#friends["friendslist"]["friends"][0]["steamid"]      # first friend on Kunjins's friend list

genres1 = fetch_genres(player1)
genres2 = fetch_genres(player2)

if genres1 and genres2:
    score = compare("player1", genres1, "player2", genres2)
    print(score)
else:
    # one of the profiles is private (or has no games), so there is nothing to compare
    print("Cannot compare: at least one player has no game data (private profile?)")

# Look up player2's profile and print the name (personaname) instead of the numeric Steam ID
player2_profile = get("ISteamUser", "GetPlayerSummaries", "v2", steamids=player2)
player2_name = player2_profile["response"]["players"][0]["personaname"]
print(player2_name)
# Look up a specific genre for a player, e.g. how many hours orbfrog has in RPG:
# print(genres1["RPG"]["hours"])
