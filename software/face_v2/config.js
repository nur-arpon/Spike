/*
 * config.js -- Spike / Spicy shared configuration.
 *
 * Names and wake words live ONLY here. Everything else reads them from this
 * object, so the owner can rename either character (Spicy's name is "for
 * now") without touching behaviour or caption code.
 *
 * Classic script (window.SPIKE), also require()-able in Node.
 */
(function (root) {
  'use strict';

  var SPIKE = {
    // ---- identity --------------------------------------------------------
    dogName: 'Spike',
    dogWakeWords: ['Spike', 'Hey Buddy'],
    catName: 'Spicy',
    catWakeWords: ['Spicy'],

    // ---- look ------------------------------------------------------------
    // Face Studio preset ids (recipe.js) used when nothing is saved yet.
    dogPreset: 'classic',
    catPreset: 'spicy',

    // ---- screen: Guition JC4827W543, 480x272 IPS, capacitive touch -------
    screenWidth: 480,
    screenHeight: 272,

    // ---- idle life (seconds) -----------------------------------------------
    blinkMin: 2.2, blinkMax: 6.0,
    doubleBlinkChance: 0.16,
    saccadeMin: 0.35, saccadeMax: 1.1,     // tiny eye jumps
    glanceMin: 2.2, glanceMax: 6.0,        // bigger look-arounds
    earFlickMin: 3.5, earFlickMax: 9.0,
    sniffMin: 7, sniffMax: 16,
    yawnEvery: 45,
    moodDrift: 20,           // how often an ignored face drifts toward bored/sulky/sleepy
    breathPeriod: 3.4,       // one breath

    // ---- battery / hunger (percent) ---------------------------------------
    hungryBelow: 30,
    weakBelow: 15,

    // ---- audio --------------------------------------------------------------
    startMuted: false,
    masterVolume: 0.6
  };

  root.SPIKE = SPIKE;
  if (typeof module !== 'undefined' && module.exports) module.exports = SPIKE;
})(typeof window !== 'undefined' ? window : global);
