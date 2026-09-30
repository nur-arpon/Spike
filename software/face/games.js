/*
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
  function drawHandIcon(ctx, choice, x, y, size, color) {
    color = color || '#FFFFFF';
    ctx.save();
    ctx.translate(x, y);
    ctx.fillStyle = color;
    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(2, size * 0.12);
    ctx.lineCap = 'round';

    if (choice === 'rock') {
      ctx.beginPath();
      ctx.arc(0, 0, size * 0.5, 0, Math.PI * 2);
      ctx.fill();
    } else if (choice === 'paper') {
      var w = size * 0.9, h = size * 1.1, r = size * 0.18;
      ctx.beginPath();
      ctx.moveTo(-w / 2 + r, -h / 2);
      ctx.lineTo(w / 2 - r, -h / 2);
      ctx.arc(w / 2 - r, -h / 2 + r, r, -Math.PI / 2, 0);
      ctx.lineTo(w / 2, h / 2 - r);
      ctx.arc(w / 2 - r, h / 2 - r, r, 0, Math.PI / 2);
      ctx.lineTo(-w / 2 + r, h / 2);
      ctx.arc(-w / 2 + r, h / 2 - r, r, Math.PI / 2, Math.PI);
      ctx.lineTo(-w / 2, -h / 2 + r);
      ctx.arc(-w / 2 + r, -h / 2 + r, r, Math.PI, Math.PI * 1.5);
      ctx.closePath();
      ctx.fill();
    } else if (choice === 'scissors') {
      ctx.beginPath();
      ctx.arc(0, 0, size * 0.42, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(-size * 0.4, -size * 0.4);
      ctx.lineTo(size * 0.4, size * 0.4);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(size * 0.4, -size * 0.4);
      ctx.lineTo(-size * 0.4, size * 0.4);
      ctx.stroke();
    }
    ctx.restore();
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
