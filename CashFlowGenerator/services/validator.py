# src/services/validator.py - 简化
"""数据校验服务"""

from typing import List, Dict, Any
from decimal import Decimal

from models.transaction import Transaction


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
        
        self._validate_balance(transactions, result)
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