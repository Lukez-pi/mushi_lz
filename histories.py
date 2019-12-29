#! /usr/bin/env python
# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import List

import numpy as np
import matplotlib as mpl
from matplotlib import pyplot as plt
import pandas as pd
import seaborn as sns
from skbio.stats.composition import centralize

@dataclass
class History():
    """base class piecewise constant history. The first epoch starts at zero,
    and the last epoch extends to infinity

    change_points: epoch change points (times)
    vals: constant values for each epoch (rows)
    """
    change_points: np.array
    vals: np.ndarray

    def __post_init__(self):
        if any(np.diff(self.change_points) <= 0) or any(
           np.isinf(self.change_points)) or any(self.change_points <= 0):
            raise ValueError('change_points must be increasing, finite, and '
                             'positive')
        if len(self.vals) != len(self.change_points) + 1:
            raise ValueError(f'len(change_points) = {len(self.change_points)}'
                             f' implies {len(self.change_points) + 1} epochs,'
                             f' but len(vals) = {len(self.vals)}')
        if np.any(self.vals < 0) or np.sum(np.isinf(self.vals)):
            raise ValueError(f'elements of vals must be finite and nonnegative')
        self.m = len(self.vals)

    def arrays(self):
        """return time grid and values in each cell"""
        t = np.concatenate((np.array([0]),
                            self.change_points,
                            np.array([np.inf])))
        return t, self.vals

    def epochs(self):
        """generator yielding epochs as tuples: (start_time, end_time, value)
        """
        for i in range(self.m):
            if i == 0:
                start_time = 0
            else:
                start_time = self.change_points[i - 1]
            if i == self.m - 1:
                end_time = np.inf
            else:
                end_time = self.change_points[i]
            value = self.vals[i]
            yield (start_time, end_time, value)

    def check_grid(self, other: int):
        """test if time grid is the same as another instance"""
        if any(self.change_points != other.change_points):
            return False
        else:
            return True

    def plot(self, t_gen: np.float = None, types=None,
             **kwargs) -> List[mpl.lines.Line2D]:
        """plot the history

        t_gen: generation time in years (optional)
        kwargs: key word arguments passed to plt.plot
        """
        t = np.concatenate((np.array([0]), self.change_points))
        if t_gen:
            t *= t_gen
            t_unit = 'years ago'
        else:
            t_unit = 'generations ago'
        if types is not None:
            idxs = [self.mutation_types.get_loc(type) for type in types]
            vals = self.vals[:, idxs]
        else:
            vals = self.vals
        lines = plt.plot(t, vals, **kwargs)
        plt.xlabel(f'$t$ ({t_unit})')
        plt.xscale('symlog')
        if 'label' in kwargs:
            plt.legend()
        plt.tight_layout()
        return lines


class η(History):
    """demographic history

    change_points: epoch change points (times)
    y: vector of constant population sizes in each epoch
    """
    @property
    def y(self):
        """read-only alias to vals attribute in base class"""
        return self.vals

    @y.setter
    def y(self, value):
        self.vals = value

    def __post_init__(self):
        super().__post_init__()
        assert len(self.y.shape) == 1, self.y.shape

    def plot(self, **kwargs) -> List[mpl.lines.Line2D]:
        lines = super().plot(**kwargs)
        plt.ylabel('$η(t)$')
        plt.yscale('log')
        plt.tight_layout()
        return lines


@dataclass
class μ(History):
    """mutation spectrum history

    change_points: epoch change points (times)
    Z: matrix of constant values for each epoch (rows) in each mutation type
       (columns)
    mutation_types: list of mutation type names (default integer names)
    """
    mutation_types: List[str] = None

    @property
    def Z(self):
        """read-only alias to vals attribute in base class"""
        return self.vals

    @Z.setter
    def Z(self, value):
        self.vals = value

    def __post_init__(self):
        super().__post_init__()
        # if mutation rate vector instead of matrix, promote to matrix
        if len(self.Z.shape) == 1:
            self.Z = self.Z[:, np.newaxis]
        assert len(self.Z.shape) == 2, self.Z.shape
        if self.mutation_types is None:
            self.mutation_types = range(1, self.Z.shape[1] + 1)
        assert len(self.mutation_types) == self.Z.shape[1]
        self.mutation_types = pd.Index(self.mutation_types,
                                       name='mutation type')

    def plot(self, types=None, normed=False,
             **kwargs) -> List[mpl.lines.Line2D]:
        """
        normed: flag to normalize to total mutation intensity
        """
        lines = super().plot(types=types, **kwargs)
        if normed:
            Z = self.Z / self.Z.sum(1, keepdims=True)
            if types is None:
                idxs = range(len(lines))
            else:
                idxs = [self.mutation_types.get_loc(type) for type in types]
            for idx, line in zip(idxs, lines):
                line.set_ydata(Z[:, idx])
            # recompute the ax.dataLim
            ax = plt.gca()
            ax.relim()
            # update ax.viewLim using the new dataLim
            ax.autoscale_view()
            # plt.ylabel('relative mutation intensity')
            plt.ylabel('mutation intensity fraction')
        else:
            plt.ylabel('$\\mu(t)$')
        plt.tight_layout()
        return lines

    def plot_cumulative(self, normed=False, **kwargs):
        """plot the cumulative mutation rate, like a Muller plot

        normed: flag to normalize to total mutation intensity
        kwargs: key word arguments passed to plt.fill_between
        """
        t = np.concatenate((np.array([0]), self.change_points))
        Z = np.cumsum(self.Z, axis=1)
        if normed:
            Z = Z / Z.sum(1, keepdims=True)
        for j in range(1, Z.shape[1]):
            plt.fill_between(t, Z[:, j - 1], Z[:, j], **kwargs)
        plt.xlabel('$t$')
        plt.ylabel('$\\mu(t)$')
        plt.xscale('symlog')
        if 'label' in kwargs:
            plt.legend()
        plt.tight_layout()

    def clustermap(self, **kwargs):
        """clustermap of compositionally centralized MUSH

        kwargs: additional keyword arguments passed to pd.clustermap
        """
        t = np.concatenate((np.array([0]), self.change_points))
        Z = centralize(self.Z)
        label = 'mutation intensity\nperturbation'
        df = pd.DataFrame(data=Z, index=pd.Index(t, name='$t$'),
                          columns=self.mutation_types)
        g = sns.clustermap(df, row_cluster=False,
                           # center=1,
                           # metric='correlation',
                           cbar_kws={'label': label},
                           **kwargs)
        # g.ax_heatmap.set_yscale('symlog')
        return g
