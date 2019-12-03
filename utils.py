import argparse
import os
import sys

import torch
from tqdm import tqdm

from go_ai import data, game
from go_ai.models import value, actorcritic
import time
import math


def hyperparameters():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=bool, default=False, help='continue from checkpoint')

    parser.add_argument('--boardsize', type=int, help='board size')
    parser.add_argument('--mcts', type=int, default=0, help='monte carlo searches')

    parser.add_argument('--temp', type=float, default=1 / 10, help='initial temperature')
    parser.add_argument('--tempsteps', type=float, default=8, help='first k steps to apply temperature to pi')
    parser.add_argument('--lr', type=float, default=1e-3, help='learning rate')

    parser.add_argument('--batchsize', type=int, default=32, help='batch size')
    parser.add_argument('--replaysize', type=int, default=200000, help='max replay memory size')
    parser.add_argument('--trainsize', type=int, default=1000 * 32, help='train data size for one iteration')

    parser.add_argument('--iterations', type=int, default=128, help='iterations')
    parser.add_argument('--episodes', type=int, default=256, help='episodes')
    parser.add_argument('--evaluations', type=int, default=256, help='episodes')
    parser.add_argument('--eval-interval', type=int, default=2, help='iterations per evaluation')

    parser.add_argument('--episodesdir', type=str, default='episodes/', help='directory to store episodes')
    parser.add_argument('--checkpath', type=str, default='bin/checkpoint.pt', help='model path for checkpoint')
    parser.add_argument('--tmppath', type=str, default='bin/tmp.pt', help='model path for temp model')

    parser.add_argument('--agent', type=str, choices=['mcts', 'ac'], default='mcts', help='type of agent/model')

    return parser.parse_args()

def parallel_play(go_env, pi1, pi2, gettraj, req_episodes):
    """
    Plays games in parallel
    :param comm:
    :param go_env:
    :param pi1:
    :param pi2:
    :param gettraj:
    :param req_episodes:
    :return:
    """
    rank = 0
    world_size = 1

    worker_episodes = int(math.ceil(req_episodes / world_size))
    episodes = worker_episodes * world_size
    single_worker = world_size <= 1

    timestart = time.time()
    winrate, steps, traj = game.play_games(go_env, pi1, pi2, gettraj, worker_episodes, progress=single_worker)
    timeend = time.time()

    duration = timeend - timestart
    avg_time = duration / worker_episodes
    avg_steps = steps / episodes

    parallel_err(rank, f'{pi1} V {pi2} | {episodes} GAMES, {avg_time:.1f} SEC/GAME, {avg_steps:.0f} STEPS/GAME, '
                       f'{100 * winrate:.1f}% WIN')
    return winrate, traj

def sync_checkpoint(rank, newcheckpoint_pi, checkpath, other_pi):
    if rank == 0:
        torch.save(newcheckpoint_pi.pytorch_model.state_dict(), checkpath)
    # Update other policy
    other_pi.pytorch_model.load_state_dict(torch.load(checkpath))


def parallel_out(rank, s, rep=0):
    """
    Only the first worker prints stuff
    :param rank:
    :param s:
    :return:
    """
    if rank == rep:
        print(s, flush=True)


def parallel_err(rank, s, rep=0):
    """
    Only the first worker prints stuff
    :param rank:
    :param s:
    :return:
    """
    if rank == rep:
        tqdm.write(f"{time.strftime('%H:%M:%S', time.localtime())}\t{s}", file=sys.stderr)
        sys.stderr.flush()


def sync_data(rank, args):
    if rank == 0:
        if args.checkpoint:
            assert os.path.exists(args.checkpath)
        else:
            # Clear worker data
            episodesdir = args.episodesdir
            data.clear_episodesdir(episodesdir)
            # Set parameters
            if args.agent == 'mcts':
                new_model = value.ValueNet(args.boardsize)
            elif args.agent == 'ac':
                new_model = actorcritic.ActorCriticNet(args.boardsize)
            torch.save(new_model.state_dict(), args.checkpath)
    parallel_err(rank, "Using checkpoint: {}".format(args.checkpoint))
