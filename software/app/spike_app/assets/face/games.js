/* face_v2 copy of ../face/games.js (v1); drawHandIcon now draws through gfx.js.
 *
 * games.js -- Rock / Paper / Scissors.
 *
 * Pure game logic (decide/playRound) plus a small drawHandIcon() built
 * from the same portable primitives as face_draw.js, so Spike's "hand"
 * can be shown on the same canvas without any images.
 */
(function (root) {
  'use strict';

  var CHOICES = ['rock', 'paper', 'scissors'];

  // beats[a] = the choice that a beats.
  var BEATS = { rock: 'scissors', paper: 'rock', scissors: 'paper' };

  function randomChoice() {
    return CHOICES[Math.floor(Math.random() * CHOICES.length)];
  }

  // Returns 'win' | 'lose' | 'draw' from the PLAYER's perspective.
  function judge(playerChoice, computerChoice) {
    if (playerChoice === computerChoice) return 'draw';
    return BEATS[playerChoice] === computerChoice ? 'win' : 'lose';
  }

  function createGame() {
    return { wins: 0, losses: 0, draws: 0, rounds: 0 };
  }

  function playRound(game, playerChoice) {
    if (CHOICES.indexOf(playerChoice) === -1) {
      throw new Error('Invalid RPS choice: ' + playerChoice);
    }
    var computerChoice = randomChoice();
    var result = judge(playerChoice, computerChoice);
    game.rounds++;
    if (result === 'win') game.wins++;
    else if (result === 'lose') game.losses++;
    else game.draws++;
    return { playerChoice: playerChoice, computerChoice: computerChoice, result: result, game: game };
  }

  // ---------------------------------------------------------------------
  // Hand icon -- rock: filled circle, paper: rounded rect, scissors: two
  // crossed "blade" lines over a small palm circle. All primitives only.
  // ---------------------------------------------------------------------
  // Spike's pick, drawn with portable Gfx primitives (gfx.js).
  // rock = fist (round + knuckles), paper = open palm, scissors = two fingers.
  function drawHandIcon(G, choice, x, y, size, color, outline) {
    color = color || '#FFFFFF';
    outline = outline || '#2E2320';
    var s = size;
    var prev = G.tag('particle');
    G.circle(x, y, s * 0.72, outline, 0.9);
    if (choice === 'rock') {
      G.circle(x, y + s * 0.05, s * 0.5, color, 1);
      for (var i = 0; i < 3; i++) G.circle(x - s * 0.26 + i * s * 0.26, y - s * 0.3, s * 0.15, color, 1);
    } else if (choice === 'paper') {
      G.rrect(x - s * 0.4, y - s * 0.1, s * 0.8, s * 0.6, s * 0.2, color, 1);
      for (var j = 0; j < 4; j++) G.rrect(x - s * 0.4 + j * s * 0.21, y - s * 0.55, s * 0.17, s * 0.55, s * 0.08, color, 1);
    } else {
      G.circle(x, y + s * 0.18, s * 0.34, color, 1);
      G.line(x - s * 0.08, y + s * 0.05, x - s * 0.3, y - s * 0.52, s * 0.18, color, 1);
      G.line(x + s * 0.08, y + s * 0.05, x + s * 0.3, y - s * 0.52, s * 0.18, color, 1);
    }
    G.tag(prev);
  }

  var api = {
    CHOICES: CHOICES,
    judge: judge,
    createGame: createGame,
    playRound: playRound,
    drawHandIcon: drawHandIcon,
    randomChoice: randomChoice
  };

  root.Games = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
