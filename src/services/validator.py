# src/services/validator.py
"""数据校验服务"""

from typing import List, Dict, Any
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.transaction import Transaction
from models.report_data import ReportData


class ValidationResult:
    """校验结果"""
    def __init__(self):
        self.is_valid: bool = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def add_error(self, error: str):
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str):
        self.warnings.append(warning)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'is_valid': self.is_valid,
            'errors': self.errors,
            'warnings': self.warnings
        }


class DataValidator:
    """数据校验器"""
    
    def __init__(self, threshold: Decimal = Decimal('0.01')):
        self.threshold = threshold
    
    def validate_transactions(self, transactions: List[Transaction]) -> ValidationResult:
        """校验交易数据"""
        result = ValidationResult()
        
        if not transactions:
            result.add_error("没有找到有效的交易数据")
            return result
        
        # 校验借贷平衡
        self._validate_balance(transactions, result)
        
        # 校验日期
        self._validate_dates(transactions, result)
        
        return result
    
    def _validate_balance(self, transactions: List[Transaction], result: ValidationResult):
        """校验借贷平衡"""
        total_debit = sum(t.debit for t in transactions)
        total_credit = sum(t.credit for t in transactions)
        
        if abs(total_debit - total_credit) > self.threshold:
            result.add_warning(
                f"借贷不平衡: 借方={total_debit:.2f}, 贷方={total_credit:.2f}, "
                f"差额={abs(total_debit - total_credit):.2f}"
            )
    
    def _validate_dates(self, transactions: List[Transaction], result: ValidationResult):
        """校验日期"""
        dates = [t.date for t in transactions if t.date]
        if not dates:
            result.add_error("没有找到有效的日期")
            return
        
        min_date = min(dates)
        max_date = max(dates)
        result.warnings.append(f"日期范围: {min_date.date()} 至 {max_date.date()}")
    
    def validate_report_data(self, report_data: ReportData) -> ValidationResult:
        """校验报表数据"""
        result = ValidationResult()
        
        if report_data.total_income == 0:
            result.add_warning("收入总额为0，请检查数据")
        
        if report_data.total_expense == 0:
            result.add_warning("支出总额为0，请检查数据")
        
        # 检查主要支出项
        if report_data.expense.get('商品采购', Decimal(0)) == 0:
            result.add_warning("商品采购支出为0，请检查采购数据")
        
        if report_data.expense.get('管理_人员薪资', Decimal(0)) == 0:
            result.add_warning("人员薪资支出为0，请检查工资数据")
        
        return result