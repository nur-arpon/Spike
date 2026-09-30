/*
 * config.js -- Spike / Spicy shared configuration.
 *
 * Names and wake words live ONLY here. Every other file reads them from
 * this object instead of hard-coding "Spike" or "Spicy" so the owner can
 * rename either character later without touching behaviour/caption code.
 *
 * Classic script (no ES modules) so it can be loaded with a plain
 * <script src="config.js"> and opened straight from file://.
 * Also usable from plain Node (for the smoke test) via module.exports.
 */
(function (root) {
  'use strict';

  var SPIKE = {
    // ---- identity -----------------------------------------------------
    dogName: 'Spike',
    dogWakeWords: ['Spike', 'Hey Buddy'],
    catName: 'Spicy',
    catWakeWords: ['Spicy'],

    // ---- look -----------------------------------------------------------
    // Any of these can be overridden at runtime from the control panel;
    // these are just the defaults on first load.
    eyeColor: '#FFFFFF',
    backgroundColor: '#000000',
    accentColor: '#59D9FF',

    // ---- screen ---------------------------------------------------------
    // Guition JC4827W543: 480x272 IPS capacitive touch.
    screenWidth: 480,
    screenHeight: 272,

    // ---- behaviour tuning -------------------------------------------------
    idleBlinkMinMs: 2200,
    idleBlinkMaxMs: 6000,
    doubleBlinkChance: 0.12,
    idleGlanceMinMs: 1800,
    idleGlanceMaxMs: 4500,
    yawnChanceMs: 45000,
    moodDriftMs: 20000, // how often an ignored mood is nudged toward bored/sulk/sleepy
    ignoredSulkMs: 60000,
    ignoredSleepMs: 150000,

    // ---- audio ------------------------------------------------------------
    startMuted: false,
    masterVolume: 0.6
  };

  root.SPIKE = SPIKE;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = SPIKE;
  }
})(typeof window !== 'undefined' ? window : global);
