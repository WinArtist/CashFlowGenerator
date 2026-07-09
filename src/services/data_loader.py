# src/services/data_loader.py
"""数据加载服务 - 优化版"""

import pandas as pd
from decimal import Decimal
from datetime import datetime
from typing import List, Optional, Dict, Tuple
from pathlib import Path
import re

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.transaction import EnhancedTransaction
from config import Config
from services.quarter_mapper import QuarterMapper


class DataLoader:
    """数据加载器 - 优化版"""
    
    def __init__(self, config: Config, quarter_mapper: Optional[QuarterMapper] = None):
        self.config = config
        self.file_config = config.file
        self.data_config = config.data
        self.quarter_mapper = quarter_mapper
        self._sheet_patterns = []
        for pattern in self.file_config.detail_sheet_patterns:
            if pattern.endswith('*'):
                self._sheet_patterns.append(('startswith', pattern[:-1]))
            else:
                self._sheet_patterns.append(('regex', re.compile(pattern, re.IGNORECASE)))
    
    def load_from_files(self, file_paths: Optional[List[str]] = None) -> List:
        if file_paths is None:
            file_paths = self.file_config.detail_files
            if not file_paths:
                file_paths = [str(self.file_config.get_input_path())]
        
        all_transactions = []
        for file_path in file_paths:
            transactions = self.load_from_file(file_path)
            all_transactions.extend(transactions)
            print(f"从 {file_path} 加载了 {len(transactions)} 笔交易")
        
        return all_transactions
    
    def load_from_file(self, file_path: str) -> List:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            print(f"文件不存在: {file_path}")
            return []
        
        all_transactions = []
        
        try:
            excel_file = pd.ExcelFile(file_path)
            sheet_names = excel_file.sheet_names
            
            for sheet_name in sheet_names:
                if self._match_sheet_pattern(sheet_name):
                    transactions, opening_balance = self._load_from_sheet(file_path, sheet_name)
                    all_transactions.extend(transactions)
                    if transactions:
                        print(f"  从工作表 [{sheet_name}] 加载了 {len(transactions)} 笔交易")
                        if opening_balance is not None:
                            print(f"  期初余额: {opening_balance:.2f}")
        except Exception as e:
            print(f"读取文件失败: {e}")
        
        return all_transactions
    
    def _match_sheet_pattern(self, sheet_name: str) -> bool:
        for pattern_type, pattern in self._sheet_patterns:
            if pattern_type == 'startswith':
                if sheet_name.startswith(pattern):
                    return True
            else:
                if pattern.search(sheet_name):
                    return True
        
        if not self._sheet_patterns and ('明细' in sheet_name or '明细账' in sheet_name):
            return True
        
        return False
    
    def _load_from_sheet(self, file_path: str, sheet_name: str) -> Tuple[List, Optional[Decimal]]:
        """加载工作表数据，同时返回期初余额"""
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, dtype=str)
            transactions, opening_balance = self._parse_dataframe_optimized(df, sheet_name)
            return transactions, opening_balance
        except Exception as e:
            print(f"读取工作表 [{sheet_name}] 失败: {e}")
            return [], None
    
    def _parse_dataframe_optimized(self, df: pd.DataFrame, sheet_name: str) -> Tuple[List, Optional[Decimal]]:
        """优化的DataFrame解析，同时提取期初余额"""
        header_row = self._find_header_row(df)
        if header_row < 0:
            return [], None

        col_index = self._find_column_indices(df, header_row)
        if not col_index or 'voucher' not in col_index:
            return [], None

        voucher_idx = col_index.get('voucher')
        date_idx = col_index.get('date')
        debit_idx = col_index.get('debit')
        credit_idx = col_index.get('credit')
        desc_idx = col_index.get('desc')
        contra_idx = col_index.get('contra')
        balance_idx = col_index.get('balance')

        if voucher_idx is None or date_idx is None or debit_idx is None or credit_idx is None:
            return [], None

        # ===== 提取期初余额（第6行I列） =====
        opening_balance = self._extract_opening_balance(df)

        data_df = df.iloc[header_row + 1:].copy()
        skip_vouchers = self.data_config.skip_vouchers

        transactions = []

        for idx, row in data_df.iterrows():
            voucher = row.iloc[voucher_idx]
            if pd.isna(voucher):
                continue
            voucher = str(voucher).strip()

            if not voucher or voucher in skip_vouchers:
                continue

            # 获取金额
            debit_val = row.iloc[debit_idx] if pd.notna(row.iloc[debit_idx]) else 0
            credit_val = row.iloc[credit_idx] if pd.notna(row.iloc[credit_idx]) else 0

            try:
                debit = Decimal(str(debit_val)) if debit_val else Decimal(0)
                credit = Decimal(str(credit_val)) if credit_val else Decimal(0)
            except:
                debit = Decimal(0)
                credit = Decimal(0)

            if debit == 0 and credit == 0:
                continue

            # 日期
            date_val = row.iloc[date_idx]
            if pd.isna(date_val):
                continue

            try:
                if isinstance(date_val, datetime):
                    date = date_val
                else:
                    date = pd.to_datetime(date_val)
            except:
                continue

            if date is None:
                continue

            description = str(row.iloc[desc_idx]) if desc_idx is not None and pd.notna(row.iloc[desc_idx]) else ''
            contra_subject = str(row.iloc[contra_idx]) if contra_idx is not None and pd.notna(row.iloc[contra_idx]) else ''

            # ===== 读取余额 =====
            balance = None
            if balance_idx is not None and balance_idx < len(row):
                balance_val = row.iloc[balance_idx]
                if pd.notna(balance_val):
                    try:
                        balance = Decimal(str(balance_val))
                    except:
                        pass

            transaction = EnhancedTransaction(
                date=date,
                voucher=voucher,
                description=description,
                debit=debit,
                credit=credit,
                contra_subject=contra_subject,
                sheet_name=sheet_name,
                row_index=idx,
                balance=balance
            )

            if self.quarter_mapper:
                self._apply_quarter_mapping(transaction)

            transactions.append(transaction)

        return transactions, opening_balance
    
    def _extract_opening_balance(self, df: pd.DataFrame) -> Optional[Decimal]:
        """
        从明细账中提取期初余额
        位置：第6行 I列（索引5行，索引8列）
        """
        try:
            # 第6行是索引5，I列是索引8
            if len(df) > 5 and len(df.iloc[5]) > 8:
                val = df.iloc[5, 8]
                if pd.notna(val):
                    # 尝试转换为Decimal
                    try:
                        # 去除可能的逗号、空格等
                        clean_val = str(val).replace(',', '').replace(' ', '').strip()
                        result = Decimal(clean_val)
                        print(f"  📊 期初余额（第6行I列）: {result:.2f}")
                        return result
                    except:
                        pass
            
            # 备用方法：查找"期初余额"文本
            for row_idx in range(min(10, len(df))):
                row = df.iloc[row_idx]
                for col_idx in range(min(10, len(row))):
                    cell_val = str(row.iloc[col_idx]) if pd.notna(row.iloc[col_idx]) else ''
                    if '期初余额' in cell_val:
                        # 找到期初余额文本，读取同一行I列
                        if len(row) > 8:
                            balance_val = row.iloc[8]
                            if pd.notna(balance_val):
                                try:
                                    clean_val = str(balance_val).replace(',', '').replace(' ', '').strip()
                                    result = Decimal(clean_val)
                                    print(f"  📊 期初余额（查找'期初余额'）: {result:.2f}")
                                    return result
                                except:
                                    pass
                        break
            
            print("  ⚠️ 未找到期初余额")
            return None
            
        except Exception as e:
            print(f"  ❌ 提取期初余额失败: {e}")
            return None
    
    def _find_header_row(self, df: pd.DataFrame) -> int:
        for idx in range(min(len(df), 20)):
            row = df.iloc[idx]
            for col in range(min(len(row), 30)):
                val = str(row.iloc[col]) if pd.notna(row.iloc[col]) else ''
                if '凭证字号' in val:
                    return idx
        return -1
    
    def _find_column_indices(self, df: pd.DataFrame, header_row: int) -> Dict[str, int]:
        if header_row < 0:
            return {}
        
        header = df.iloc[header_row]
        col_index = {}
        
        for i, val in enumerate(header):
            if pd.notna(val):
                val_str = str(val).strip()
                if '日期' in val_str:
                    col_index['date'] = i
                elif '凭证字号' in val_str:
                    col_index['voucher'] = i
                elif '摘要' in val_str:
                    col_index['desc'] = i
                elif '对方科目' in val_str:
                    col_index['contra'] = i
                elif '借方' in val_str:
                    col_index['debit'] = i
                elif '贷方' in val_str:
                    col_index['credit'] = i
                elif '方向' in val_str:
                    col_index['direction'] = i
                elif '余额' in val_str:
                    col_index['balance'] = i
        
        # 如果没找到余额列，默认使用I列（索引8）
        if 'balance' not in col_index and len(header) > 8:
            val_str = str(header.iloc[8]) if pd.notna(header.iloc[8]) else ''
            if '余额' in val_str:
                col_index['balance'] = 8
            else:
                # 强制使用I列作为余额列
                col_index['balance'] = 8
                print(f"  ℹ️ 未找到'余额'列，默认使用I列（索引8）作为余额列")
        
        return col_index
    
    def _apply_quarter_mapping(self, transaction: EnhancedTransaction):
        if self.quarter_mapper:
            result = self.quarter_mapper.map_quarter(
                date=transaction.date,
                voucher=transaction.voucher,
                sheet_name=transaction.sheet_name,
                month=transaction.date.month if transaction.date else None
            )
            transaction.quarter = result.quarter
            transaction.quarter_confidence = result.confidence
            transaction.quarter_strategy = result.strategy.value
            transaction.quarter_matched_rule = result.matched_rule