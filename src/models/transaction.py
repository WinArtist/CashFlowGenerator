# src/models/transaction.py
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class Transaction:
    """基础交易"""
    date: datetime
    voucher: str
    description: str
    debit: Decimal
    credit: Decimal
    contra_subject: str = ""
    amount: Decimal = Decimal(0)
    is_income: bool = False
    income_type: Optional[str] = None
    
    def __post_init__(self):
        """计算金额和类型"""
        if self.debit > 0:
            self.amount = self.debit
            self.is_income = True
        elif self.credit > 0:
            self.amount = self.credit
            self.is_income = False


@dataclass
class EnhancedTransaction(Transaction):
    """增强交易"""
    sheet_name: str = ""
    row_index: int = -1
    quarter: Optional[str] = None
    quarter_confidence: float = 0.0
    quarter_strategy: str = ""
    quarter_matched_rule: Optional[str] = None
    
    def __post_init__(self):
        """调用父类的 __post_init__"""
        super().__post_init__()


@dataclass
class ClassifiedTransaction(EnhancedTransaction):
    """分类交易"""
    income_category: Optional[str] = None
    expense_category: Optional[str] = None
    classification_confidence: float = 0.0
    
    def __post_init__(self):
        """调用父类的 __post_init__"""
        super().__post_init__()