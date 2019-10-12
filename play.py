import gym

from go_ai import policies, game

# Environment
BOARD_SIZE = 4
go_env = gym.make('gym_go:go-v0', size=BOARD_SIZE)

# Policies
random_policy = policies.RandomPolicy()
greedy_policy = policies.MctPolicy('Greedy', val_func=policies.greedy_val_func, num_searches=0, temp=0)
greedy_mct_policy = policies.MctPolicy('MCT', val_func=policies.greedy_val_func, num_searches=128, temp=0)
human_policy = policies.HumanPolicy()

game.pit(go_env, human_policy, greedy_mct_policy, False)
