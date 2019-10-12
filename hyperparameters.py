BOARD_SIZE = 4
BATCH_SIZE = 32

ITERATIONS = 256
EPISODES_PER_ITERATION = 256
NUM_EVAL_GAMES = 256

INIT_TEMP = 1
TEMP_DECAY = 3 / 4
MIN_TEMP = 1 / 64

NUM_SEARCHES = 16

LOAD_SAVED_MODELS = False
EPISODES_DIR = 'episodes/'
CHECKPOINT_PATH = 'checkpoints/checkpoint_{}x{}.pt'.format(BOARD_SIZE, BOARD_SIZE)

DEMO_TRAJECTORY_PATH = 'logs/a_trajectory.png'
