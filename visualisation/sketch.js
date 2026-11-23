// Steam network visualisation
// Reads network.json (made by fetch.py) and draws players as dots and friendships as lines.
//
// The file has five parts:
//   0) SCAN FIELD - the text field where you type a Steam ID to scan.
//   1) LOOKS      - colours, sizes, fonts. This is where you design the look.
//   2) DATA       - loading network.json and turning it into objects we can draw.
//   3) PHYSICS    - forces that pull friends together and push everyone else apart.
//   4) DRAWING    - setup() and draw(), which p5 runs for us.
//
// The sketch must be opened through server.py (http://localhost:8080/visualisation/),
// because the server is the one that talks to Steam when you scan.


// ======================================================================
// 0) SCAN FIELD - type a Steam ID, press Enter or click Scan
// ======================================================================

let steamIdInput;   // the text field
let scanButton;
let statusText;     // small text next to the button that says what is happening
let scanning = false;

// Makes the text field, button and status text in the top left corner. Called from setup().
function setupScanField() {
  steamIdInput = createInput("");
  steamIdInput.attribute("placeholder", "Steam ID (17 digits)");
  steamIdInput.position(16, 16);
  const buttonX = 16 + steamIdInput.width + 8;     // 8 pixels to the right of the text field

  scanButton = createButton("Scan");
  scanButton.position(buttonX, 16);
  scanButton.mousePressed(startScan);

  statusText = createSpan("");
  statusText.position(buttonX + scanButton.width + 12, 18);
  statusText.style("color", LABEL_COLOR);
  statusText.style("font-family", "sans-serif");

  // Pressing Enter in the text field also starts the scan
  steamIdInput.elt.addEventListener("keydown", event => {
    if (event.key === "Enter") startScan();
  });
}

// Asks server.py to scan the Steam ID: the player plus all their friends.
// While the scan runs - and afterwards, while the server is still fetching game tags in the
// background - we reload network.json every 2 seconds, so you can watch the network grow and
// the grey dots get their colours.
async function startScan() {
  if (scanning) return;                     // only one scan at a time
  const steamId = steamIdInput.value().trim();
  if (!/^\d{17}$/.test(steamId)) {
    statusText.html("A Steam ID must be 17 digits");
    return;
  }

  scanning = true;
  statusText.html("Scanning " + steamId + " and friends...");
  startAutoReload();

  try {
    const response = await fetch("/scan?steamid=" + steamId);
    if (response.status === 404) {
      // The page is served by something that doesn't know /scan, e.g. "python3 -m http.server"
      statusText.html("This server can't scan - start it with: .venv/bin/python server.py");
    } else {
      const result = await response.json();
      if (response.ok) {
        statusText.html(`Scan done: ${result.players} players, ${result.friendships} friendships`);
      } else {
        statusText.html("Error: " + (result.error || response.status));
      }
    }
  } catch (error) {
    // fetch() itself failed (no server at all) or the answer wasn't JSON (server.py crashed)
    statusText.html("Could not reach server.py - is it running? (see its terminal for errors)");
    console.log("Scan failed:", error);
  }

  scanning = false;
  reloadNetwork();     // reloadNetwork stops the auto reload once no more tags are waiting
}

// Reloading every 2 seconds: started by a scan, stopped by reloadNetwork when everything is done.
let reloadTimer = null;

function startAutoReload() {
  if (!reloadTimer) reloadTimer = setInterval(reloadNetwork, 2000);
}

function stopAutoReload() {
  clearInterval(reloadTimer);
  reloadTimer = null;
}


// ======================================================================
// 1) LOOKS - change these to design the network
// ======================================================================

const BACKGROUND = "#111111";

const NODE_SIZE = 20;             // diameter of a player dot in pixels
const EDGE_COLOR = "#555555";
const EDGE_WEIGHT = 1;            // line thickness in pixels
const LABEL_COLOR = "#ffffff";
const LABEL_SIZE = 12;

// The colour of each genre. A player's dot gets the colour of their top_genre.
// Add a line for each genre you see in network.json.
const GENRE_COLORS = {
  "Shooter": "#e05d44",
  "Simulation": "#4a90d9",
  "RPG": "#FDFFA4",
  "Survival": "#6CA273",
  "Sports": "#884195",
  "Horror": "#381B1B"
};
const UNKNOWN_GENRE_COLOR = "#999999";   // used for genres that aren't in the list above
const HIDDEN_PLAYER_COLOR = "#555555";   // players who hide their playtime on Steam (top_genre is null)

// Picks the colour for a player
function playerColor(node) {
  if (node.top_genre === null) return HIDDEN_PLAYER_COLOR;
  return GENRE_COLORS[node.top_genre] || UNKNOWN_GENRE_COLOR;
}


// Draws ONE player. Change this to change how a player looks.
// node has: node.x, node.y, node.name, node.top_genre, node.id
function drawNode(node) {
  noStroke();
  fill(playerColor(node));
  circle(node.x, node.y, NODE_SIZE);

  fill(LABEL_COLOR);
  textSize(LABEL_SIZE);
  textAlign(CENTER, TOP);
  text(node.name, node.x, node.y + NODE_SIZE / 2 + 4);
}

// Draws ONE friendship line between two players. Change this to change how a line looks.
// edge has: edge.source and edge.target (the two player objects, with .x and .y)
function drawEdge(edge) {
  stroke(EDGE_COLOR);
  strokeWeight(EDGE_WEIGHT);
  line(edge.source.x, edge.source.y, edge.target.x, edge.target.y);
}


// ======================================================================
// 2) DATA - loading network.json
// ======================================================================

let data;          // the raw content of network.json
let nodes = [];    // the players, with a position (x, y) added
let edges = [];    // the friendships, pointing to the player objects instead of IDs

// p5 runs preload() before setup() and waits until the file is loaded.
// The path is "../network.json" because network.json is in the folder above this one.
function preload() {
  data = loadJSON("../network.json");
}

// Turns the data from network.json into nodes and edges we can draw.
// It can be called again and again with new data (see reloadNetwork below):
// players we already have KEEP their position, only new players get a new position.
function buildNetwork() {
  // Look-up table of the nodes we already have: player ID -> node
  const oldNodeById = {};
  for (const node of nodes) {
    oldNodeById[node.id] = node;
  }

  nodes = data.nodes.map(player => {
    const old = oldNodeById[player.id];
    if (old) {
      // Known player: take the new info from the file (e.g. a new top_genre), but keep position and speed
      return { ...player, x: old.x, y: old.y, vx: old.vx, vy: old.vy };
    }
    // New player: random position, standing still. The physics (section 3) moves it to a good place.
    return {
      ...player,
      x: random(width * 0.1, width * 0.9),
      y: random(height * 0.1, height * 0.9),
      vx: 0,     // speed in x direction (pixels per frame)
      vy: 0,     // speed in y direction
    };
  });

  // Look-up table: player ID -> node, so we can find a node quickly from its ID
  const nodeById = {};
  for (const node of nodes) {
    nodeById[node.id] = node;
  }

  // In the file, source and target are IDs (text). Here we swap them for the actual nodes,
  // so drawEdge() can just use edge.source.x instead of searching for the node every frame.
  edges = data.edges
    .map(edge => ({
      ...edge,
      source: nodeById[edge.source],
      target: nodeById[edge.target],
    }))
    // Skip a line if one of its players is missing from the file, so drawEdge() never crashes
    .filter(edge => edge.source && edge.target);
}

// Prints how many players have each genre as their top_genre, most common first.
// Genres without a colour in GENRE_COLORS are marked, so you know which ones to add.
function logGenreCounts() {
  const counts = {};
  for (const node of nodes) {
    counts[node.top_genre] = (counts[node.top_genre] || 0) + 1;
  }
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  console.log("Top genres (players):");
  for (const [genre, count] of sorted) {
    if (genre === "null") {      // object keys are text, so null becomes "null"
      console.log(`  (hidden playtime): ${count}`);
      continue;
    }
    const note = GENRE_COLORS[genre] ? "" : "   <- no colour yet";
    console.log(`  ${genre}: ${count}${note}`);
  }
}

// Loads network.json again WITHOUT reloading the page, and updates the network.
// "?t=" + the current time makes the URL different each time, so the browser can't
// give us an old saved copy of the file.
function reloadNetwork() {
  loadJSON(
    "../network.json?t=" + Date.now(),
    newData => {
      const before = nodes.length;
      data = newData;
      buildNetwork();
      if (nodes.length !== before) {
        console.log(`Network reloaded: ${nodes.length} players (${nodes.length - before} new), ${edges.length} friendships`);
      }

      // tags_waiting = games the server is still fetching tags for in the background
      const waiting = data.tags_waiting || 0;
      if (waiting > 0) {
        startAutoReload();                  // keep reloading until all tags have arrived
        if (!scanning) statusText.html(`Fetching game tags: ${waiting} left (about ${ceil(waiting / 60)} min)`);
      } else if (reloadTimer && !scanning) {
        stopAutoReload();                   // scan and tags are done: stop reloading
        statusText.html(`Done: ${nodes.length} players, ${edges.length} friendships`);
        logGenreCounts();
      }
    },
    // If loading fails, keep the network we have and just try again next time
    () => console.log("Could not reload network.json, keeping the old network")
  );
}

// p5 runs keyPressed() every time a key is pressed.
// Press R to reload network.json (e.g. after running fetch.py again).
function keyPressed() {
  // Don't reload when you type an "r" in the text field
  if (document.activeElement === steamIdInput.elt) return;
  if (key === "r" || key === "R") {
    reloadNetwork();
    setTimeout(logGenreCounts, 500);        // print the genre list once the reload has arrived
  }
}


// ======================================================================
// 3) PHYSICS - moves the players so friends end up close together
// ======================================================================
// Three forces (the same ideas as the Coding Train spring videos):
//   - every pair of players PUSHES each other away, so dots don't pile up
//   - every friendship line is a SPRING that PULLS the two friends together
//   - a weak pull towards the CENTRE, so the network stays on screen
// Change the numbers to change how the network behaves.

const REPULSION = 800;         // how hard players push each other away
const SPRING_LENGTH = 60;      // the length a friendship line "wants" to be (pixels)
const SPRING_STRENGTH = 0.01;  // how hard a friendship line pulls
const CENTER_PULL = 0.002;     // how hard everything is pulled towards the middle
const DAMPING = 0.85;          // friction: 1 = never slows down, 0 = stops at once

function updatePhysics() {
  // 1) Push: every pair of players once
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i];
      const b = nodes[j];
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const distSq = max(dx * dx + dy * dy, 25);   // at least 5 px apart, so the push can't explode
      const dist = sqrt(distSq);
      const force = REPULSION / distSq;             // closer = stronger push
      // Push along the line between the two, in opposite directions
      a.vx += (dx / dist) * force;
      a.vy += (dy / dist) * force;
      b.vx -= (dx / dist) * force;
      b.vy -= (dy / dist) * force;
    }
  }

  // 2) Pull: every friendship line works like a spring (Hooke's law: force = strength x stretch)
  for (const edge of edges) {
    const a = edge.source;
    const b = edge.target;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = max(sqrt(dx * dx + dy * dy), 1);
    const stretch = dist - SPRING_LENGTH;           // positive = too long (pull), negative = too short (push)
    const force = SPRING_STRENGTH * stretch;
    a.vx += (dx / dist) * force;
    a.vy += (dy / dist) * force;
    b.vx -= (dx / dist) * force;
    b.vy -= (dy / dist) * force;
  }

  // 3) Pull towards the centre, then apply friction and move
  for (const node of nodes) {
    node.vx += (width / 2 - node.x) * CENTER_PULL;
    node.vy += (height / 2 - node.y) * CENTER_PULL;
    node.vx *= DAMPING;
    node.vy *= DAMPING;
    node.x += node.vx;
    node.y += node.vy;
  }
}


// ======================================================================
// 4) DRAWING - p5 runs setup() once, then draw() about 60 times per second
// ======================================================================

function setup() {
  createCanvas(windowWidth, windowHeight);
  buildNetwork();
  logGenreCounts();
  setupScanField();
  // If the page is opened while the server is still fetching tags, keep reloading until it's done
  if (data.tags_waiting > 0) startAutoReload();
}

function draw() {
  updatePhysics();
  background(BACKGROUND);

  // Lines first, so the dots are drawn on top of them
  for (const edge of edges) {
    drawEdge(edge);
  }
  for (const node of nodes) {
    drawNode(node);
  }
}

// Make the canvas follow the window size
function windowResized() {
  resizeCanvas(windowWidth, windowHeight);
}
