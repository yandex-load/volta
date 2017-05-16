# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd
from scipy import interpolate
from scipy import signal
import queue as q
import logging


logger = logging.getLogger(__name__)


class SyncFinder(object):
    """
    Calculates sync points for volta current measurements and phone system logs

    Parameters
    ----------
        config : dict
            module configuration
        sync_q : queue-like object, should be able to answer to put()/get_nowait()
            contains pandas DataFrames w/ sync events
        grabber_q : queue-like object, should be able to answer to put()/get_nowait()
            contains pandas DataFrames w/ volta electrical current measurements events
        sample_rate : int
            volta box sample rate (depends on what type of volta box and software you use)

    Returns
    -------
        dict
            offsets for 'volta timestamp -> system log timestamp' and 'volta timestamp -> custom log timestamp'

    """
    def __init__(self, config, sample_rate):
        self.search_interval = config.get('search_interval', 30)
        self.sample_rate = sample_rate
        self.sync_df = pd.DataFrame()
        self.volta_sync_stage_df = pd.DataFrame()

    def put(self, data, type):
        if type == 'sync':
            self.sync_df = self.sync_df.append(data)
        elif type == 'currents':
            if len(self.volta_sync_stage_df) < (self.search_interval * self.sample_rate):
                self.volta_sync_stage_df = self.volta_sync_stage_df.append(data)

    def find_sync_points(self):
        logger.info('Starting sync...')

        if len(self.sync_df) == 0:
            raise ValueError('No sync events found!')

        logger.debug('Sync df contents:\n %s', self.sync_df)
        self.__prepare_sync_df()
        logger.debug('Sync df after preparation:\n %s', self.sync_df)
        logger.debug('Sync stage volta currents dataframe:\n %s', self.volta_sync_stage_df)

        if len(self.volta_sync_stage_df) < (self.search_interval * self.sample_rate):
            raise ValueError('Not enough electrical currents for sync')

        refsig = self.ref_signal(self.sync_df)
        logger.debug('Refsignal len: %s, Refsignal contents:\n %s', len(refsig), refsig)

        cc = self.cross_correlate(self.volta_sync_stage_df['current'], refsig, (self.search_interval * self.sample_rate))
        logger.debug('Cross correlation: %s', cc)

        # which volta sample is a first sync event
        volta_to_sync_offset_sample = np.argmax(cc)
        logger.debug('Volta to syslog offset sample: %s', volta_to_sync_offset_sample)

        # which volta uts is a first sync event
        volta_to_sync_offset_uts = self.volta_sync_stage_df.iloc[volta_to_sync_offset_sample].name
        logger.debug('Sync point volta utimestamp: %s', volta_to_sync_offset_uts)

        sync = {}
        # offset volta -> system uts
        sync['sys_uts_offset'] = int(volta_to_sync_offset_uts - self.sync_df[self.sync_df.message > 0].iloc[0].name)
        # offset volta -> log uts
        sync['log_uts_offset'] = int(volta_to_sync_offset_uts - self.sync_df[self.sync_df.message > 0].iloc[0]["log_uts"])

        sync['sync_sample'] = volta_to_sync_offset_sample

        logger.info('Sync results: %s', sync)
        return sync

    def __prepare_sync_df(self):
        """
        append dfs from sync queue, reset idx, map sync events and make offset
        """
        # map messages
        self.sync_df.message = self.sync_df.message.map({'rise': 1, 'fall': 0})

        # drop sync events after search interval - we don't need this
        self.sync_df = self.sync_df[self.sync_df.index < self.sync_df.index[0] + (self.search_interval * 10 ** 6)]

        # offset
        self.sync_df['sample_offset'] = self.sync_df.index.map(
            lambda x: (
                (x - self.sync_df.index[0])
            ) * self.sample_rate // 10**6
        )
        return

    def ref_signal(self, sync):
        """
        Generate square reference signal
        """
        logger.info("Generating ref signal...")
        if len(sync) == 0:
            raise ValueError('Sync events not found.')
        f = interpolate.interp1d(sync["sample_offset"], sync["message"], kind="zero")
        X = np.linspace(0, sync["sample_offset"].values[-1], sync["sample_offset"].values[-1])
        rs = f(X)
        return rs - np.mean(rs)

    def cross_correlate(self, sig, ref, first=30000):
        """
        Calculate cross-correlation with lag. Take only first n lags.
        """
        logger.info("Calculating cross-correlation...")
        return signal.fftconvolve(sig[:first], ref[::-1], mode="valid")
