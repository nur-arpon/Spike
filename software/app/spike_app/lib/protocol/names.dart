/// Names shared with PROTOCOL.md, face_v2 (moods.js, actions.js) and the
/// brain (spike_brain/protocol.py). `test/protocol_names_test.dart` checks
/// these lists against the face_v2 copies bundled in assets/face, so they
/// cannot drift.
library;

const int protocolVersion = 1;

/// The spec release this app implements (PROTOCOL.md changelog); the wire `v` stays 1.
const String protocolRelease = '1.3';
const int defaultPort = 8765;
const int maxMessageBytes = 64 * 1024;

const List<String> moods = [
  'neutral', 'happy', 'excited', 'love', 'laughing', 'playful', 'curious',
  'sad', 'caring', 'sleepy', 'sleeping', 'bored', 'sulking', 'scared',
  'surprised', 'cuteAngry', 'dizzy', 'proud', 'embarrassed', 'begging',
  'cuddly', 'wakeupAlarm',
  'joy', 'delight', 'anger', 'frustration', 'disgust', 'grief',
  'loneliness', 'hope', 'shyness', 'jealousy', 'confusion', 'suspicion',
  'relief', 'gratitude', 'mischief', 'determination', 'nervousness',
  'awe', 'smugness', 'silliness', 'hungry', //
];

const Map<String, String> moodLabels = {
  'neutral': 'Neutral', 'happy': 'Happy', 'excited': 'Excited', 'love': 'Love',
  'laughing': 'Laughing', 'playful': 'Playful', 'curious': 'Curious',
  'sad': 'Sad', 'caring': 'Caring', 'sleepy': 'Sleepy', 'sleeping': 'Sleeping',
  'bored': 'Bored', 'sulking': 'Sulking', 'scared': 'Scared', 'surprised': 'Surprised',
  'cuteAngry': 'Cute-angry', 'dizzy': 'Dizzy', 'proud': 'Proud', 'embarrassed': 'Embarrassed',
  'begging': 'Begging', 'cuddly': 'Cuddly', 'wakeupAlarm': 'Wake-up alarm',
  'joy': 'Joy', 'delight': 'Delight', 'anger': 'Anger', 'frustration': 'Frustration',
  'disgust': 'Disgust', 'grief': 'Grief', 'loneliness': 'Lonely', 'hope': 'Hope',
  'shyness': 'Shy', 'jealousy': 'Jealous', 'confusion': 'Confused', 'suspicion': 'Suspicious',
  'relief': 'Relief', 'gratitude': 'Grateful', 'mischief': 'Mischief',
  'determination': 'Determined', 'nervousness': 'Nervous', 'awe': 'Awe',
  'smugness': 'Smug', 'silliness': 'Silly', 'hungry': 'Hungry',
};

/// Human label for a mood id (falls back to the id itself).
String moodLabel(String? mood) => moodLabels[mood] ?? (mood ?? '');

/// face_v2 ACTIONS plus the v1.1 comfort actions and the v1.4 body actions.
const List<String> actions = [
  'wakeUp', 'fallAsleep', 'napping', 'dozing', 'deepSleepDreams', 'tripBump',
  'sneeze', 'hiccup', 'shiver', 'pant', 'tailWagDance', 'zoomies', 'headTilt',
  'sniffAround', 'beggingAction', 'rollOver', 'playBow', 'yawn', 'boop',
  'snuggle', 'slowWag', 'walk', 'paw', //
];
const List<String> comfortActions = ['snuggle', 'slowWag'];

/// v1.4 (PROTOCOL.md 5.2): robot-side only, like the comfort actions, but with no
/// face_v2 fallback motion at all (not even in the simulator).
const List<String> bodyActions = ['walk', 'paw'];
const List<String> actionDirections = ['forward', 'back'];
const List<int> actionSteps = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16];
const List<String> actionStyles = ['auto', 'tiltStep', 'rearStep', 'march'];
const List<String> actionSides = ['left', 'right'];
const List<String> actionFroms = ['stand', 'sit'];

const List<String> events = [
  'sayHi', 'greetByTimeOfDay', 'comeHome', 'ownerLooksSad', 'pickedUp',
  'fellOver', 'ignoredNudge', //
];
const List<String> sounds = [
  'yip', 'bark', 'whine', 'sniff', 'sigh', 'snore', 'giggle', 'meow', 'purr',
  'hiss', 'trill', 'yawn', 'sneeze', 'hiccup', 'growl', 'munch', 'pop', 'boop',
  'patSqueak', //
];
const List<String> modes = ['dog', 'cat'];
const List<String> roles = ['simulator', 'face', 'camera', 'robot', 'tool', 'app']; // app: v1.2

/// The brain's language model (v1.2 brain_status.llm).
const List<String> llmStates = ['ready', 'warming', 'asleep', 'off'];
const List<String> caps = [
  'face', 'speaker', 'mic', 'camera', 'touch', 'imu', 'edge', 'battery', 'drive', 'text', //
];
const List<String> listenStates = ['idle', 'wake', 'listening', 'thinking', 'speaking'];
const List<String> touchZones = ['head', 'nose', 'back', 'chin'];
const List<String> touchGestures = ['tap', 'pat', 'hold', 'release'];
const List<String> imuEvents = ['pickup', 'putdown', 'shake', 'fall', 'lap'];
const List<String> edgeSensors = ['front_left', 'front_right', 'rear_left', 'rear_right'];
const List<String> sayStates = ['started', 'finished', 'stopped'];
const List<String> alarmStates = ['ringing', 'snoozed', 'stopped'];
const List<String> gamePhases = ['start', 'countdown', 'shoot', 'reveal', 'end'];
const List<String> rpsChoices = ['rock', 'paper', 'scissors', 'unknown'];
const List<String> errorCodes = [
  'bad_json', 'missing_field', 'bad_value', 'unknown_type', 'version_mismatch',
  'not_ready', 'auth', 'too_big', 'busy', //
];

/// Close codes (PROTOCOL.md section 3).
abstract final class CloseCodes {
  static const normal = 1000;
  static const goingAway = 1001;
  static const helloTimeout = 4000;
  static const versionMismatch = 4001;
  static const abuse = 4002;
  static const auth = 4003;
}
