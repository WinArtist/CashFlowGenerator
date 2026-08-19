# src/models/report_data.py - 删除季度相关
"""报表数据模型"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Set, Optional

from models.transaction import ClassifiedTransaction


@dataclass
class ReportData:
    """报表数据"""
    income: Dict[str, Decimal] = field(default_factory=dict)
    expense: Dict[str, Decimal] = field(default_factory=dict)
    total_income: Decimal = Decimal(0)
    total_expense: Decimal = Decimal(0)
    net_flow: Decimal = Decimal(0)
    transaction_count: int = 0
    categories: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        if self.income is None:
            self.income = {}
        if self.expense is None:
            self.expense = {}
        if self.categories is None:
            self.categories = set()
    
    def add_transaction(self, classified: ClassifiedTransaction):
        """添加已分类的交易"""
        self.transaction_count += 1
        
        if classified.is_income:
            category = classified.income_category or "其他收入"
            self.income[category] = self.income.get(category, Decimal(0)) + classified.amount
            self.total_income += classified.amount
        else:
            category = classified.expense_category or "其他支出"
            self.expense[category] = self.expense.get(category, Decimal(0)) + classified.amount
            self.total_expense += classified.amount
        
        if classified.income_category:
            self.categories.add(classified.income_category)
        if classified.expense_category:
            self.categories.add(classified.expense_category)
        
        self.net_flow = self.total_income - self.total_expense
    
    def get_expense_by_prefix(self, prefix: str) -> Decimal:
        """根据前缀获取支出合计"""
        if not prefix:
            return Decimal(0)
        total = Decimal(0)
        for k, v in self.expense.items():
            if k and k.startswith(prefix):
                total += v
        return total
    
    def get_income_by_prefix(self, prefix: str) -> Decimal:
        """根据前缀获取收入合计"""
        if not prefix:
            return Decimal(0)
        total = Decimal(0)
        for k, v in self.income.items():
            if k and k.startswith(prefix):
                total += v
        return total
    
    def to_dict(self) -> Dict:
        return {
            'income': {k: float(v) for k, v in self.income.items() if v > 0},
            'expense': {k: float(v) for k, v in self.expense.items() if v > 0},
            'total_income': float(self.total_income),
            'total_expense': float(self.total_expense),
            'net_flow': float(self.net_flow),
            'transaction_count': self.transaction_count,
            'categories': list(self.categories)
        }