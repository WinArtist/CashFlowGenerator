# src/models/transaction.py - 修复版（删除 EnhancedTransaction）
"""交易数据模型"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class Transaction:
    """交易数据"""
    date: datetime
    voucher: str
    description: str
    debit: Decimal
    credit: Decimal
    contra_subject: str = ""
    sheet_name: str = ""
    row_index: int = -1
    balance: Optional[Decimal] = None
    amount: Decimal = Decimal(0)
    is_income: bool = False
    
    def __post_init__(self):
        """计算金额和类型"""
        if self.debit > 0:
            self.amount = self.debit
            self.is_income = True
        elif self.credit > 0:
            self.amount = self.credit
            self.is_income = False


@dataclass
class ClassifiedTransaction(Transaction):
    """已分类的交易"""
    income_category: Optional[str] = None
    expense_category: Optional[str] = None
    classification_confidence: float = 0.0
    
    def __post_init__(self):
        super().__post_init__()