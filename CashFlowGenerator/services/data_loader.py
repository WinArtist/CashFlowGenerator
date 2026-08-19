# src/services/data_loader.py - 修复版（删除 EnhancedTransaction 引用）
"""数据加载服务"""

import pandas as pd
from decimal import Decimal
from datetime import datetime
from typing import List, Optional, Dict, Tuple
from pathlib import Path
import re

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.transaction import Transaction
from CashFlowGenerator.config import Config


class DataLoader:
    """数据加载器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.file_config = config.file
        self.data_config = config.data
        self._sheet_patterns = []
        for pattern in self.file_config.detail_sheet_patterns:
            if pattern.endswith('*'):
                self._sheet_patterns.append(('startswith', pattern[:-1]))
            else:
                self._sheet_patterns.append(('regex', re.compile(pattern, re.IGNORECASE)))
    
    def load_from_files(self, file_paths: Optional[List[str]] = None) -> List[Transaction]:
        """从多个文件加载交易数据"""
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
    
    def load_from_file(self, file_path: str) -> List[Transaction]:
        """从单个文件加载交易数据"""
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
                    transactions = self._load_from_sheet(file_path, sheet_name)
                    all_transactions.extend(transactions)
                    if transactions:
                        print(f"  从工作表 [{sheet_name}] 加载了 {len(transactions)} 笔交易")
        except Exception as e:
            print(f"读取文件失败: {e}")
        
        return all_transactions
    
    def _match_sheet_pattern(self, sheet_name: str) -> bool:
        """匹配工作表名称模式"""
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
    
    def _load_from_sheet(self, file_path: str, sheet_name: str) -> List[Transaction]:
        """加载工作表数据"""
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, dtype=str)
            return self._parse_dataframe(df, sheet_name)
        except Exception as e:
            print(f"读取工作表 [{sheet_name}] 失败: {e}")
            return []
    
    def _parse_dataframe(self, df: pd.DataFrame, sheet_name: str) -> List[Transaction]:
        """解析DataFrame提取交易数据"""
        header_row = self._find_header_row(df)
        if header_row < 0:
            return []

        col_index = self._find_column_indices(df, header_row)
        if not col_index or 'voucher' not in col_index:
            return []

        voucher_idx = col_index.get('voucher')
        date_idx = col_index.get('date')
        debit_idx = col_index.get('debit')
        credit_idx = col_index.get('credit')
        desc_idx = col_index.get('desc')
        contra_idx = col_index.get('contra')
        balance_idx = col_index.get('balance')

        if voucher_idx is None or date_idx is None or debit_idx is None or credit_idx is None:
            return []

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

            balance = None
            if balance_idx is not None and balance_idx < len(row):
                balance_val = row.iloc[balance_idx]
                if pd.notna(balance_val):
                    try:
                        balance = Decimal(str(balance_val))
                    except:
                        pass

            transaction = Transaction(
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

            transactions.append(transaction)

        return transactions
    
    def _find_header_row(self, df: pd.DataFrame) -> int:
        """查找表头行"""
        for idx in range(min(len(df), 20)):
            row = df.iloc[idx]
            for col in range(min(len(row), 30)):
                val = str(row.iloc[col]) if pd.notna(row.iloc[col]) else ''
                if '凭证字号' in val:
                    return idx
        return -1
    
    def _find_column_indices(self, df: pd.DataFrame, header_row: int) -> Dict[str, int]:
        """查找列索引"""
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
        
        if 'balance' not in col_index and len(header) > 8:
            col_index['balance'] = 8
            print(f"  ℹ️ 未找到'余额'列，默认使用I列（索引8）作为余额列")
        
        return col_index
    
    def get_opening_balance(self, file_path: str) -> Optional[Decimal]:
        """从明细账中提取期初余额（第6行I列）"""
        try:
            df = pd.read_excel(file_path, header=None, dtype=str)
            if len(df) > 5 and len(df.iloc[5]) > 8:
                val = df.iloc[5, 8]
                if pd.notna(val):
                    clean_val = str(val).replace(',', '').replace(' ', '').strip()
                    return Decimal(clean_val)
            return None
        except Exception as e:
            print(f"提取期初余额失败: {e}")
            return None