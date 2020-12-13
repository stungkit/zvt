# -*- coding: utf-8 -*-
import pandas as pd

from jqdatapy import get_token, get_money_flow
from zvt import zvt_config
from zvt.api import generate_kdata_id
from zvt.contract import IntervalLevel
from zvt.contract.api import df_to_db
from zvt.contract.recorder import FixedCycleDataRecorder
from zvt.domain import StockMoneyFlow, Stock
from zvt.recorders.joinquant.common import to_jq_entity_id
from zvt.recorders.joinquant.misc.joinquant_index_money_flow_recorder import JoinquantIndexMoneyFlowRecorder
from zvt.utils import pd_is_not_null, to_time_str
from zvt.utils.time_utils import TIME_FORMAT_DAY


class JoinquantStockMoneyFlowRecorder(FixedCycleDataRecorder):
    entity_provider = 'joinquant'
    entity_schema = Stock

    provider = 'joinquant'
    data_schema = StockMoneyFlow

    def __init__(self, entity_type='stock', exchanges=['sh', 'sz'], entity_ids=None, codes=None, batch_size=10,
                 force_update=True, sleeping_time=0, default_size=2000, real_time=False, fix_duplicate_way='ignore',
                 start_timestamp=None, end_timestamp=None, close_hour=0, close_minute=0, level=IntervalLevel.LEVEL_1DAY,
                 kdata_use_begin_time=False, one_day_trading_minutes=24 * 60) -> None:
        super().__init__(entity_type, exchanges, entity_ids, codes, batch_size, force_update, sleeping_time,
                         default_size, real_time, fix_duplicate_way, start_timestamp, end_timestamp, close_hour,
                         close_minute, level, kdata_use_begin_time, one_day_trading_minutes)
        get_token(zvt_config['jq_username'], zvt_config['jq_password'], force=True)

    def generate_domain_id(self, entity, original_data):
        return generate_kdata_id(entity_id=entity.id, timestamp=original_data['timestamp'], level=self.level)

    def on_finish(self):
        # 根据 个股资金流 计算 大盘资金流
        JoinquantIndexMoneyFlowRecorder().run()

    def record(self, entity, start, end, size, timestamps):
        if not self.end_timestamp:
            df = get_money_flow(code=to_jq_entity_id(entity),
                                date=to_time_str(start))
        else:
            df = get_money_flow(code=to_jq_entity_id(entity),
                                date=start, end_date=to_time_str(self.end_timestamp))

        df = df.dropna()

        if pd_is_not_null(df):
            df['name'] = entity.name
            df.rename(columns={'date': 'timestamp',
                               'net_amount_main': 'net_main_inflows',
                               'net_pct_main': 'net_main_inflow_rate',

                               'net_amount_xl': 'net_huge_inflows',
                               'net_pct_xl': 'net_huge_inflow_rate',

                               'net_amount_l': 'net_big_inflows',
                               'net_pct_l': 'net_big_inflow_rate',

                               'net_amount_m': 'net_medium_inflows',
                               'net_pct_m': 'net_medium_inflow_rate',

                               'net_amount_s': 'net_small_inflows',
                               'net_pct_s': 'net_small_inflow_rate'
                               }, inplace=True)

            # 转换到标准float
            df[['net_main_inflows', 'net_huge_inflows', 'net_big_inflows', 'net_medium_inflows', 'net_small_inflows']] = \
                df[['net_main_inflows', 'net_huge_inflows', 'net_big_inflows', 'net_medium_inflows',
                    'net_small_inflows']].apply(lambda x: x * 10000)

            df[['net_main_inflow_rate', 'net_huge_inflow_rate', 'net_big_inflow_rate', 'net_medium_inflow_rate',
                'net_small_inflow_rate']] = \
                df[['net_main_inflow_rate', 'net_huge_inflow_rate', 'net_big_inflow_rate', 'net_medium_inflow_rate',
                    'net_small_inflow_rate']].apply(lambda x: x / 100)

            # 计算总流入
            df['net_inflows'] = df['net_huge_inflows'] + df['net_big_inflows'] + df['net_medium_inflows'] + df[
                'net_small_inflows']
            # 计算总流入率
            amount = df['net_main_inflows'] / df['net_main_inflow_rate']
            df['net_inflow_rate'] = df['net_inflows'] / amount

            df['entity_id'] = entity.id
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['provider'] = 'joinquant'
            df['code'] = entity.code

            def generate_kdata_id(se):
                return "{}_{}".format(se['entity_id'], to_time_str(se['timestamp'], fmt=TIME_FORMAT_DAY))

            df['id'] = df[['entity_id', 'timestamp']].apply(generate_kdata_id, axis=1)

            df = df.drop_duplicates(subset='id', keep='last')

            df_to_db(df=df, data_schema=self.data_schema, provider=self.provider, force_update=self.force_update)

        return None


if __name__ == '__main__':
    JoinquantStockMoneyFlowRecorder(start_timestamp='2020-12-01').run()
