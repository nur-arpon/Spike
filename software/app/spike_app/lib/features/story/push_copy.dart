/// Every word of the robot "push" (the preview banner, the robot cards, the "imagine this on your desk"
/// sheets, the 3-day reminder and the story page) lives HERE, in one place, so it is easy to edit and
/// easy to check: test/story_test.dart scans all of it and fails if anything claims a thing the real
/// body cannot do (core/capabilities.dart). Plain English, no developer words.
///
/// The founder's note is not here: it is the text file assets/story/founder_note.txt (the product and
/// publisher names must not be typed into code, and a text file is the easiest thing to edit).
/// The waitlist link is not here either: it is `robotWaitlistUrl` in brand.json.
library;

/// Where "Follow the build" goes while no waitlist form exists yet (the website's robot page).
const robotPageUrl = 'https://nur-arpon.github.io/Spike/robot.html';

/// The five tabs that carry a robot card.
enum PushTab { home, play, talk, studio, life }

/// The little overline on every card.
const cardOverline = 'SPIKE\'S ROBOT BODY';

/// (title, one line) for the robot card at the end of each tab.
const tabCards = <PushTab, (String, String)>{
  PushTab.home: ('His body is being built', 'See how far he has come, and be first in line.'),
  PushTab.play: ('Imagine these tricks on your desk', 'Bows, head tilts, snuggles and happy wags, for real.'),
  PushTab.talk: ('Soon he\'ll answer from your desk', 'The same Spike, with a little body and a face to look at.'),
  PushTab.studio: ('This face will be on his real screen', 'The one you design here is the face he will wear.'),
  PushTab.life: ('He\'ll wake you up in person', 'Your alarms and reminders, on your desk, with his face.'),
};

/// The preview banner at the top of Home.
const bannerTitle = 'Preview: Spike\'s robot body is on the way';
const bannerLine = 'This app came first. Tap to see how he\'s coming along.';

/// The features the first-use "imagine this on your desk" peek can be about (once each, ever).
enum PeekFeature { trick, wag, drive, sleep }

const peekHeadline = 'Imagine this on your desk';

const peekLines = <PeekFeature, String>{
  PeekFeature.trick: 'Soon he\'ll do tricks right in front of you, a bow, a head tilt, a happy wiggle.',
  PeekFeature.wag: 'That happy wag will be his real tail, wagging on your desk.',
  PeekFeature.drive: 'Soon you\'ll steer him across your desk yourself. Desk-edge stops are always on.',
  PeekFeature.sleep: 'He\'ll lie down and drift off on your desk, a little dog with his screen dimmed.',
};

/// The story page.
const storyTitle = 'Spike\'s story';
const storyHeadline = 'Meet the robot behind the app';
const storySub = 'A small dog with a screen for a face, made for your desk.';
const storyBeginTitle = 'How it started';
const storyThingsTitle = 'What he\'ll do on your desk';
const storyThingsSub = 'Only things his body really does.';
const storyInDevelopment = 'In development';
const storyBuildTitle = 'How the build is going';
const storyFounderTitle = 'A note from the founder';
const storyViewer = 'Turn him around in 3D';

/// "(company) is a one-person startup by (founder) ..." is built in the page from brand.json names
/// ([startupLine]); this is the rest of it.
String startupLine(String company, String founder) =>
    '$company is a one-person startup by $founder. This app came first, so Spike is already here. '
    'His robot body is being built right now.';

const ctaWaitlist = 'I want one — join the waitlist';
const ctaFollow = 'Follow the build';
const ctaNote = 'The form opens in your browser. This app doesn\'t collect anything.';
const ctaNoteFollow = 'Opens his website in your browser. This app doesn\'t collect anything.';

/// The reminder every three days.
const reminderTitle = 'Spike\'s body is still being built';
const reminderLine = 'Here is how far along he is.';
const laterLabel = 'Not now';
const storyLink = 'See the whole story';

/// Every string above, for the test that scans the copy.
List<String> allPushCopy() => [
      cardOverline,
      for (final e in tabCards.values) ...[e.$1, e.$2],
      bannerTitle,
      bannerLine,
      peekHeadline,
      ...peekLines.values,
      storyTitle,
      storyHeadline,
      storySub,
      storyBeginTitle,
      storyThingsTitle,
      storyThingsSub,
      storyBuildTitle,
      storyFounderTitle,
      startupLine('company', 'founder'),
      ctaWaitlist,
      ctaFollow,
      ctaNote,
      ctaNoteFollow,
      reminderTitle,
      reminderLine,
      storyLink,
    ];
