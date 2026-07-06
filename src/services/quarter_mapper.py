# src/services/quarter_mapper.py
"""季度映射服务 - 支持多种映射策略"""

from datetime import datetime
from typing import Optional, Dict, List
import re
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import QuarterMappingConfig, QuarterMappingStrategy, MonthMappingRule, VoucherPrefixRule, SheetNameRule


@dataclass
class QuarterMappingResult:
    """季度映射结果"""
    quarter: str
    strategy: QuarterMappingStrategy
    confidence: float
    matched_rule: Optional[str] = None


class QuarterMapper:
    """季度映射器 - 支持多种策略灵活配置"""
    
    def __init__(self, config: QuarterMappingConfig):
        self.config = config
        self._compiled_patterns = {}
        self._compile_patterns()
    
    def _compile_patterns(self):
        """预编译正则表达式"""
        # 编译凭证号规则
        for rule in self.config.voucher_rules:
            pattern = re.compile(f"^{re.escape(rule.prefix)}", re.IGNORECASE)
            self._compiled_patterns[f"voucher_{rule.prefix}"] = (pattern, rule)
        
        # 编译工作表名规则
        for rule in self.config.sheet_rules:
            if self.config.fuzzy_match:
                pattern = re.compile(re.escape(rule.keyword), re.IGNORECASE)
            else:
                pattern = re.compile(f"^{re.escape(rule.keyword)}", re.IGNORECASE)
            self._compiled_patterns[f"sheet_{rule.keyword}"] = (pattern, rule)
    
    def map_quarter(self, 
                    date: Optional[datetime] = None,
                    voucher: Optional[str] = None,
                    sheet_name: Optional[str] = None,
                    month: Optional[int] = None) -> QuarterMappingResult:
        """
        根据配置的策略映射季度
        
        优先级：
        1. 凭证号前缀规则（最高）
        2. 工作表名规则
        3. 自定义月份规则
        4. 默认月份映射
        5. 默认季度
        """
        
        # 1. 根据凭证号前缀匹配
        if voucher and self.config.voucher_rules:
            result = self._match_by_voucher(voucher)
            if result:
                return result
        
        # 2. 根据工作表名匹配
        if sheet_name and self.config.sheet_rules:
            result = self._match_by_sheet_name(sheet_name)
            if result:
                return result
        
        # 3. 根据月份匹配（优先使用自定义规则）
        target_month = month or (date.month if date else None)
        if target_month is not None:
            result = self._match_by_month(target_month)
            if result:
                return result
        
        # 4. 默认季度
        return QuarterMappingResult(
            quarter=self.config.default_quarter,
            strategy=QuarterMappingStrategy.CUSTOM_RULE,
            confidence=0.3,
            matched_rule="default"
        )
    
    def _match_by_voucher(self, voucher: str) -> Optional[QuarterMappingResult]:
        """根据凭证号匹配"""
        for key, (pattern, rule) in self._compiled_patterns.items():
            if key.startswith("voucher_") and pattern.search(voucher):
                return QuarterMappingResult(
                    quarter=rule.target_quarter,
                    strategy=QuarterMappingStrategy.BY_VOUCHER_PREFIX,
                    confidence=1.0,
                    matched_rule=f"voucher_prefix:{rule.prefix}"
                )
        return None
    
    def _match_by_sheet_name(self, sheet_name: str) -> Optional[QuarterMappingResult]:
        """根据工作表名匹配"""
        for key, (pattern, rule) in self._compiled_patterns.items():
            if key.startswith("sheet_") and pattern.search(sheet_name):
                confidence = 0.9 if self.config.fuzzy_match else 1.0
                return QuarterMappingResult(
                    quarter=rule.target_quarter,
                    strategy=QuarterMappingStrategy.BY_SHEET_NAME,
                    confidence=confidence,
                    matched_rule=f"sheet_keyword:{rule.keyword}"
                )
        return None
    
    def _match_by_month(self, month: int) -> Optional[QuarterMappingResult]:
        """根据月份匹配"""
        # 优先使用自定义规则
        for rule in self.config.month_rules:
            if rule.month == month:
                return QuarterMappingResult(
                    quarter=rule.target_quarter,
                    strategy=QuarterMappingStrategy.BY_MONTH_MAPPING,
                    confidence=1.0,
                    matched_rule=f"month_rule:{month}->{rule.target_quarter}"
                )
        
        # 使用默认映射
        if month in self.config.month_mapping:
            return QuarterMappingResult(
                quarter=self.config.month_mapping[month],
                strategy=QuarterMappingStrategy.BY_DATE,
                confidence=0.95,
                matched_rule=f"date_mapping:{month}->{self.config.month_mapping[month]}"
            )
        
        return None
    
    def batch_map_quarters(self, transactions: List[Dict]) -> List[Dict]:
        """批量映射季度"""
        for trans in transactions:
            result = self.map_quarter(
                date=trans.get('date'),
                voucher=trans.get('voucher'),
                sheet_name=trans.get('sheet_name'),
                month=trans.get('month')
            )
            trans['quarter'] = result.quarter
            trans['quarter_confidence'] = result.confidence
            trans['quarter_strategy'] = result.strategy.value
            trans['quarter_matched_rule'] = result.matched_rule
        
        return transactions


class QuarterMapperBuilder:
    """季度映射器构建器 - 提供便捷的配置方法"""
    
    def __init__(self):
        self.config = QuarterMappingConfig()
    
    def use_date_based(self) -> 'QuarterMapperBuilder':
        """使用基于日期的映射（默认）"""
        self.config.strategy = QuarterMappingStrategy.BY_DATE
        return self
    
    def use_custom_month_mapping(self, mapping: Dict[int, str]) -> 'QuarterMapperBuilder':
        """使用自定义月份映射"""
        self.config.strategy = QuarterMappingStrategy.BY_MONTH_MAPPING
        self.config.month_mapping.update(mapping)
        return self
    
    def add_month_rule(self, month: int, quarter: str, description: str = "") -> 'QuarterMapperBuilder':
        """添加月份规则"""
        self.config.add_month_rule(month, quarter, description)
        return self
    
    def add_voucher_rule(self, prefix: str, quarter: str, description: str = "") -> 'QuarterMapperBuilder':
        """添加凭证号前缀规则"""
        self.config.add_voucher_rule(prefix, quarter, description)
        return self
    
    def add_sheet_rule(self, keyword: str, quarter: str, description: str = "") -> 'QuarterMapperBuilder':
        """添加工作表名规则"""
        self.config.add_sheet_rule(keyword, quarter, description)
        return self
    
    def set_default_quarter(self, quarter: str) -> 'QuarterMapperBuilder':
        """设置默认季度"""
        self.config.default_quarter = quarter
        return self
    
    def enable_fuzzy_match(self, enabled: bool = True) -> 'QuarterMapperBuilder':
        """启用模糊匹配"""
        self.config.fuzzy_match = enabled
        return self
    
    def build(self) -> QuarterMapper:
        """构建季度映射器"""
        return QuarterMapper(self.config)
    
    def build_config(self) -> QuarterMappingConfig:
        """构建配置对象"""
        return self.config