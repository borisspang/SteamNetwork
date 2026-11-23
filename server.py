# A small local web server, so the p5 sketch can ask Python to scan a Steam player.
#
# Why do we need it? p5 runs in the browser, and the browser can't call the Steam API
# (the API key would be visible, and Steam blocks requests from web pages).
# So p5 asks THIS server, and the server uses the functions in fetch.py.
#
# Start it from the project folder with:   .venv/bin/python server.py
# Then open:                              http://localhost:8080/visualisation/

import os
import re
from flask import Flask, jsonify, redirect, request, send_from_directory

import fetch   # our own fetch.py: scan(), load_network() etc.

ROOT = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=None)


# http://localhost:8080/ -> send the browser on to the visualisation
@app.route("/")
def home():
    return redirect("/visualisation/")


# The p5 files (index.html, sketch.js, style.css).
# We only serve files from the visualisation folder and network.json, so files
# like .env (with the API key) can never be opened from the browser.
@app.route("/visualisation/")
@app.route("/visualisation/<path:filename>")
def visualisation(filename="index.html"):
    return send_from_directory(os.path.join(ROOT, "visualisation"), filename)


# p5 loads the network from here. We don't send the raw file: we add each player's top_genre,
# worked out with the newest tag_rules.py. So edit tag_rules.py, refresh the page, and the colours change.
@app.route("/network.json")
def network_file():
    response = jsonify(fetch.network_with_genres())
    response.headers["Cache-Control"] = "no-store"   # always send the newest version
    return response


# p5 calls this with /scan?steamid=7656...
# It scans the player and their friends, and answers when the scan is done.
@app.route("/scan")
def scan():
    steam_id = request.args.get("steamid", "").strip()

    # A numeric Steam ID is always 17 digits. Check it, so we don't send nonsense to Steam.
    if not re.fullmatch(r"\d{17}", steam_id):
        return jsonify(error="A Steam ID must be 17 digits"), 400

    network = fetch.scan(steam_id)
    return jsonify(players=len(network["nodes"]), friendships=len(network["edges"]),
                   tags_waiting=fetch.tags_waiting())


if __name__ == "__main__":
    # Fetch game tags in the background, so scans don't wait 1 second per new game
    fetch.start_tag_worker()
    # threaded=True: the server can send network.json to p5 WHILE a scan is running,
    # so the sketch can show the network growing.
    app.run(port=8080, threaded=True)
