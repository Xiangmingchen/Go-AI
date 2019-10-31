import gym
import numpy as np
import torch
import torch.nn as nn
from tqdm import tqdm

from go_ai import data

gymgo = gym.make('gym_go:go-v0', size=0)
GoGame = gymgo.gogame
GoVars = gymgo.govars


class ValueNet(nn.Module):
    def __init__(self, board_size):
        super(ValueNet, self).__init__()
        self.convs = nn.Sequential(
            nn.Conv2d(GoVars.NUM_CHNLS, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.Conv2d(64, 64, 3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.Conv2d(64, 4, 3, padding=1),
            nn.BatchNorm2d(4),
            nn.ReLU(),
        )

        self.fcs = nn.Sequential(
            nn.Linear(4 * board_size ** 2, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Linear(256, 1)
        )

        self.criterion = nn.BCEWithLogitsLoss()

    def forward(self, x):
        x = self.convs(x)
        x = torch.flatten(x, start_dim=1)
        x = self.fcs(x)
        return x


def optimize(model, replay_data, optimizer, batch_size):
    N = len(replay_data[0])
    for component in replay_data:
        assert len(component) == N

    batched_data = [np.array_split(component, N // batch_size) for component in replay_data]
    batched_data = list(zip(*batched_data))

    model.train()
    running_loss = 0
    running_acc = 0
    batches = 0
    pbar = tqdm(batched_data, desc="Optimizing", leave=False)
    for i, (states, actions, next_states, rewards, terminals, wins) in enumerate(pbar, 1):
        # Augment
        states = data.batch_random_symmetries(states)

        states = torch.from_numpy(states).type(torch.FloatTensor)
        wins = torch.from_numpy(wins[:, np.newaxis]).type(torch.FloatTensor)

        optimizer.zero_grad()
        vals = model(states)
        pred_wins = (torch.sigmoid(vals) > 0.5).type(vals.dtype)
        loss = model.criterion(vals, wins)
        loss.backward()
        optimizer.step()

        running_loss += loss.item()
        running_acc += torch.mean((pred_wins == wins).type(wins.dtype)).item()
        batches = i

        pbar.set_postfix_str("{:.1f}%, {:.3f}L".format(100 * running_acc / i, running_loss / i))

    pbar.close()
    return running_acc / batches, running_loss / batches
