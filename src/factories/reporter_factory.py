# src/factories/reporter_factory.py
"""报表生成器工厂"""

from decimal import Decimal
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from strategies.classification_strategy import RuleBasedStrategy
from strategies.default_strategy import DEFAULT_CLASSIFICATION_RULES
from services.data_loader import DataLoader
from services.classifier import TransactionClassifier
from services.aggregator import DataAggregator
from services.validator import DataValidator
from services.reporter import ReportGenerator
from services.quarter_mapper import QuarterMapper


class ReporterFactory:
    """报表生成器工厂 - 负责组装各个组件"""
    
    def __init__(self, config: Optional[Config] = None, quarter_mapper: Optional[QuarterMapper] = None):
        self.config = config or Config.get_instance()
        self.quarter_mapper = quarter_mapper
        self._classifier = None
        self._data_loader = None
        self._aggregator = None
        self._validator = None
        self._report_generator = None
    
    def set_quarter_mapper(self, quarter_mapper: QuarterMapper):
        """设置季度映射器"""
        self.quarter_mapper = quarter_mapper
        # 重置数据加载器以使用新的映射器
        self._data_loader = None
    
    def create_classifier(self) -> TransactionClassifier:
        """创建分类器"""
        if self._classifier is None:
            strategy = RuleBasedStrategy(DEFAULT_CLASSIFICATION_RULES)
            self._classifier = TransactionClassifier(strategy, self.config)
        return self._classifier
    
    def create_data_loader(self) -> DataLoader:
        """创建数据加载器"""
        if self._data_loader is None:
            self._data_loader = DataLoader(self.config, self.quarter_mapper)
        return self._data_loader
    
    def create_aggregator(self) -> DataAggregator:
        """创建聚合器"""
        if self._aggregator is None:
            self._aggregator = DataAggregator()
        return self._aggregator
    
    def create_validator(self) -> DataValidator:
        """创建校验器"""
        if self._validator is None:
            threshold = self.config.data.validation_threshold
            self._validator = DataValidator(Decimal(str(threshold)))
        return self._validator
    
    def create_report_generator(self) -> ReportGenerator:
        """创建报表生成器"""
        if self._report_generator is None:
            self._report_generator = ReportGenerator(self.config)
        return self._report_generator