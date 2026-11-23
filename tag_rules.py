# Rules for turning SteamSpy tags into genres.
#
# You can edit this file while server.py is running: the server reads it again every time
# p5 loads the network. So: edit, save, refresh the page (or press R in the sketch). No restart needed.

# How much a genre is "punished" for being common in the whole network (0 to 1).
# A player's colour is the genre with the highest:  their share of games - STANDOUT_STRENGTH x network average share
#   0    = the genre they have the most games in wins (big genres like Shooter win for almost everyone)
#   1    = the genre they have the most MORE than average wins (common genres rarely win, many small genres)
#   0.75 = in between: a real shooter fan is still a shooter, but rare genres also get a chance
STANDOUT_STRENGTH = 0.75

# Tags der betyder (næsten) det samme slås sammen til ét tag.
# Nøglen er tagget, vi finder hos SteamSpy, og værdien er det tag, vi vil bruge i stedet.
# Eksempel: "Turn-Based Combat" og "Turn-Based Strategy" bliver begge til "Turn-Based".
merged_tags = {
    "Turn-Based Combat": "Turn-Based", "Turn-Based Strategy": "Turn-Based",
    "Adventure": "RPG", "Tactical RPG": "RPG", "Action RPG": "RPG", "CRPG": "RPG", "JRPG": "RPG",
    "MMORPG": "MMO", "Massively Multiplayer": "MMO",
    "Open World Survival Craft": "Survival",
    "Dark Fantasy": "Fantasy", "FPS": "Shooter",
    "Hero Shooter": "Shooter", "Looter Shooter": "Shooter",
    "Space": "Sci-fi", "Automobile Sim": "Simulation", "Life Sim": "Simulation",
    "Online Co-Op": "Co-op", "Local Co-Op": "Co-op"
}

# Tags vi ekskluderer, fordi de beskriver HVORDAN man spiller (perspektiv, spiltilstand, pris osv.)
# og ikke hvad spillet handler om. Tilføj eller fjern tags her, efterhånden som I ser dem i outputtet.
# Excluded tags are removed both before AND after merging, so excluding "Shooter" also removes "FPS" etc.
excluded_tags = {
    "Free to Play", "Early Access", "Great Soundtrack", "Moddable",   # pris/status/ekstra
    "Third Person", "First-Person", "Isometric", "2D", "3D",          # kameraperspektiv
    "Singleplayer", "Multiplayer", "Co-op",                           # spiltilstand (Online/Local Co-Op merges into Co-op)
    "Team-Based", "Massively Multiplayer",
    "Action", "MMO", "Software", "Utilities", "Indie", "Pixel Graphics",
    "Open World", "Competitive", "Football (Soccer)",
    # Beskriver hvordan spillet ER (stemning, sværhedsgrad), ikke genren:
    "Funny", "Difficult", "Physics", "Gore", "Realistic", "Casual",
    "Local Multiplayer", "Story Rich", "PvP", "PvE", "e-sports"
}
