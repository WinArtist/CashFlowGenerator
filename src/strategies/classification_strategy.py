# src/strategies/classification_strategy.py
"""分类策略 - 策略模式实现"""

from abc import ABC, abstractmethod
from typing import Optional, Dict
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.transaction import Transaction, ClassifiedTransaction


class ClassificationStrategy(ABC):
    """分类策略抽象基类"""
    
    @abstractmethod
    def classify(self, transaction: Transaction) -> Optional[ClassifiedTransaction]:
        """分类单笔交易"""
        pass
    
    @abstractmethod
    def get_confidence(self, transaction: Transaction, category: str) -> float:
        """获取分类置信度"""
        pass


class RuleBasedStrategy(ClassificationStrategy):
    """基于规则的分类策略"""
    
    def __init__(self, rules: Dict[str, Dict]):
        self.rules = rules
        self.direct_mapping: Dict[str, str] = {}
        self.keyword_rules: Dict[str, Dict] = {}
        
        self._build_rules()
    
    def _build_rules(self):
        """构建规则索引"""
        for category, config in self.rules.items():
            # 直接映射
            for code in config.get('contra_prefixes', []):
                self.direct_mapping[code] = category
            
            # 关键词规则
            if config.get('keywords'):
                self.keyword_rules[category] = {
                    'keywords': [k.lower() for k in config['keywords']],
                    'exclude': [e.lower() for e in config.get('exclude', [])],
                    'is_income': config.get('is_income', False)
                }
    
    def _match_by_contra_code(self, transaction: Transaction) -> Optional[str]:
        """根据对方科目代码匹配"""
        for code, category in self.direct_mapping.items():
            if transaction.contra_code.startswith(code):
                return category
        return None
    
    def _match_by_keywords(self, transaction: Transaction, is_income: bool) -> Optional[str]:
        """根据关键词匹配"""
        text = transaction.search_text
        
        for category, rule in self.keyword_rules.items():
            if rule['is_income'] != is_income:
                continue
            
            for keyword in rule['keywords']:
                if keyword in text:
                    # 检查排除词
                    excluded = any(ex in text for ex in rule['exclude'])
                    if not excluded:
                        return category
        return None
    
    def classify(self, transaction: Transaction) -> Optional[ClassifiedTransaction]:
        """分类交易"""
        # 优先使用科目代码匹配
        category = self._match_by_contra_code(transaction)
        
        # 其次使用关键词匹配
        if not category:
            category = self._match_by_keywords(transaction, transaction.is_income)
        
        # 默认分类
        if not category:
            if transaction.is_income:
                category = '其他收入'
            else:
                category = '管理_其他'
        
        confidence = self.get_confidence(transaction, category)
        return ClassifiedTransaction(transaction, category, confidence)
    
    def get_confidence(self, transaction: Transaction, category: str) -> float:
        """获取分类置信度"""
        if transaction.contra_code and transaction.contra_code in self.direct_mapping:
            return 1.0
        return 0.7