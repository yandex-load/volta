# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd
import logging
from scipy import interpolate
from scipy import signal

from volta.common.interfaces import DataListener

pd.options.mode.chained_assignment = None

logger = logging.getLogger(__name__)


class SyncFinder(DataListener):
    """ Calculates sync points for volta current measurements and phone system logs

    Attributes:
        search_interval (int): amount of seconds will be used for sync (searching for sync events)
        sample_rate (int): volta box sample rate - depends on software and which type of volta box you use
    """
    def __init__(self, config):
        super(SyncFinder, self).__init__(config)
        self.search_interval = config.get_option('sync', 'search_interval')
        self.sample_rate = None
        self.sync_df = pd.DataFrame()
        self.volta_sync_stage_df = pd.DataFrame()

    def put(self, data, type):
        """ Append sync chunks to sync dataframe
            Append currents dataframes until search interval won't will be filled up
        """
        if type == 'sync':
            self.sync_df = self.sync_df.append(data)
        elif type == 'currents':
            if len(self.volta_sync_stage_df) < (self.search_interval * self.sample_rate):
                self.volta_sync_stage_df = self.volta_sync_stage_df.append(data)

    def find_sync_points(self):
        """ Cross correlation and calculate offsets

        Returns:
            dict: offsets for 'volta timestamp -> system log timestamp' and 'volta timestamp -> custom log timestamp'
        """
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

        cc = self.cross_correlate(
            self.volta_sync_stage_df['value'],
            refsig,
            (self.search_interval * self.sample_rate)
        )
        logger.debug('Cross correlation: %s', cc)

        # [sample_offset] volta sample <-> first sync event
        first_sync_offset_sample = np.argmax(cc)
        logger.debug('[sample_offset] volta sample <-> first sync event: %s', first_sync_offset_sample)

        # [uts_offset] volta uts <-> first sync event
        sync_offset = self.volta_sync_stage_df.iloc[first_sync_offset_sample]['uts']
        logger.debug('[uts_offset] volta uts <-> first sync event: %s', sync_offset)

        return {
            # [uts_offset] volta uts <-> phone system uts
            'sys_uts_offset':  int(
                sync_offset - self.sync_df[self.sync_df.message > 0].iloc[0]['sys_uts']
            ),
            # [uts_offset] volta uts <-> phone log uts
            'log_uts_offset': int(
                sync_offset - self.sync_df[self.sync_df.message > 0].iloc[0]["log_uts"]
            ),
            'sync_sample': first_sync_offset_sample
        }

    def __prepare_sync_df(self):
        """ Reset idx, drop excessive sync data, map sync events and make offset """
        # map messages
        self.sync_df.loc[:, ('message')] = self.sync_df.message.map({'rise': 1, 'fall': 0})
        self.sync_df.reset_index(inplace=True)

        # drop sync events after search interval - we don't need this
        self.sync_df = self.sync_df[self.sync_df.sys_uts < self.sync_df.sys_uts[0] + (self.search_interval * 10 ** 6)]

        # offset
        self.sync_df.loc[:, ('sample_offset')] = self.sync_df['sys_uts'].map(
            lambda x: (
                (x - self.sync_df['sys_uts'][0])
            ) * self.sample_rate // 10**6
        )

    @staticmethod
    def ref_signal(sync):
        """ Generate square reference signal """
        logger.info("Generating ref signal...")
        if len(sync) == 0:
            raise ValueError('Sync events not found.')
        f = interpolate.interp1d(sync["sample_offset"], sync["message"], kind="zero")
        X = np.linspace(0, sync["sample_offset"].values[-1], sync["sample_offset"].values[-1])
        rs = f(X)
        return rs - np.mean(rs)

    @staticmethod
    def cross_correlate(sig, ref, first=30000):
        """ Calculate cross-correlation with lag. Take only first n lags """
        logger.info("Calculating cross-correlation...")
        return signal.fftconvolve(sig[:first], ref[::-1], mode="valid")

    def close(self):
        return

    def get_info(self):
        return
