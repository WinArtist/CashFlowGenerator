# src/models/report_data.py
"""报表数据模型"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Set
from datetime import datetime

from models.transaction import ClassifiedTransaction


@dataclass
class QuarterReportData:
    """季度报表数据"""
    income: Dict[str, Decimal] = field(default_factory=dict)
    expense: Dict[str, Decimal] = field(default_factory=dict)
    total_income: Decimal = Decimal(0)
    total_expense: Decimal = Decimal(0)
    
    def add_income(self, category: str, amount: Decimal):
        """添加收入"""
        if not category:
            category = "其他收入"
        self.income[category] = self.income.get(category, Decimal(0)) + amount
        self.total_income += amount
    
    def add_expense(self, category: str, amount: Decimal):
        """添加支出"""
        if not category:
            category = "其他支出"
        category = str(category) if category is not None else "其他支出"
        self.expense[category] = self.expense.get(category, Decimal(0)) + amount
        self.total_expense += amount
    
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


@dataclass
class ReportData:
    """报表数据"""
    income: Dict[str, Decimal] = field(default_factory=dict)
    expense: Dict[str, Decimal] = field(default_factory=dict)
    quarterly: Dict[str, QuarterReportData] = field(default_factory=dict)
    total_income: Decimal = Decimal(0)
    total_expense: Decimal = Decimal(0)
    net_flow: Decimal = Decimal(0)
    transaction_count: int = 0
    categories: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        """初始化后处理，确保字典存在"""
        if self.income is None:
            self.income = {}
        if self.expense is None:
            self.expense = {}
        if self.quarterly is None:
            self.quarterly = {}
        if self.categories is None:
            self.categories = set()
    
    def add_transaction(self, classified: ClassifiedTransaction):
        """添加已分类的交易"""
        self.transaction_count += 1
        
        quarter = classified.quarter or "Q2"
        
        # 确保季度数据结构存在
        if quarter not in self.quarterly:
            self.quarterly[quarter] = QuarterReportData()
        
        quarter_data = self.quarterly[quarter]
        
        if classified.is_income:
            # 收入
            category = classified.income_category or "其他收入"
            category = str(category) if category is not None else "其他收入"
            
            self.income[category] = self.income.get(category, Decimal(0)) + classified.amount
            self.total_income += classified.amount
            quarter_data.add_income(category, classified.amount)
        else:
            # 支出
            category = classified.expense_category or "其他支出"
            category = str(category) if category is not None else "其他支出"
            
            self.expense[category] = self.expense.get(category, Decimal(0)) + classified.amount
            self.total_expense += classified.amount
            quarter_data.add_expense(category, classified.amount)
        
        # 记录分类
        if classified.income_category:
            self.categories.add(classified.income_category)
        if classified.expense_category:
            self.categories.add(classified.expense_category)
        
        # 计算净现金流
        self.net_flow = self.total_income - self.total_expense
    
    def get_expense_by_prefix(self, prefix: str) -> Decimal:
        """根据前缀获取支出合计"""
        if not prefix:
            return Decimal(0)
        total = Decimal(0)
        if self.expense:
            for k, v in self.expense.items():
                if k and k.startswith(prefix):
                    total += v
        return total
    
    def get_income_by_prefix(self, prefix: str) -> Decimal:
        """根据前缀获取收入合计"""
        if not prefix:
            return Decimal(0)
        total = Decimal(0)
        if self.income:
            for k, v in self.income.items():
                if k and k.startswith(prefix):
                    total += v
        return total
    
    def get_category_total(self, category: str) -> Decimal:
        """获取某个分类的合计"""
        if not category:
            return Decimal(0)
        if category in self.income:
            return self.income.get(category, Decimal(0))
        if category in self.expense:
            return self.expense.get(category, Decimal(0))
        return Decimal(0)
    
    def get_quarter_data(self, quarter: str) -> QuarterReportData:
        """获取季度数据"""
        if quarter not in self.quarterly:
            self.quarterly[quarter] = QuarterReportData()
        return self.quarterly[quarter]
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'income': {k: float(v) for k, v in self.income.items() if v > 0},
            'expense': {k: float(v) for k, v in self.expense.items() if v > 0},
            'total_income': float(self.total_income),
            'total_expense': float(self.total_expense),
            'net_flow': float(self.net_flow),
            'transaction_count': self.transaction_count,
            'categories': list(self.categories)
        }