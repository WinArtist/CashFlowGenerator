# src/config.py - 优化后的配置管理模块（删除季度相关）
"""配置管理模块 - 支持从YAML加载分类规则"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import yaml


class Environment(Enum):
    """环境枚举"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


@dataclass
class ContraSubjectRule:
    """对方科目规则"""
    keywords: List[str] = field(default_factory=list)
    target_category: str = ""
    description: str = ""
    fuzzy: bool = False


@dataclass
class IncomeCategoryRule:
    """收入分类规则"""
    category: str = ""
    contra_rules: List[ContraSubjectRule] = field(default_factory=list)
    summary_keywords: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ExpenseCategoryRule:
    """支出分类规则"""
    category: str = ""
    contra_rules: List[ContraSubjectRule] = field(default_factory=list)
    summary_keywords: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ClassificationConfig:
    """分类配置 - 支持从YAML加载，带预编译缓存"""
    income_rules: List[IncomeCategoryRule] = field(default_factory=list)
    expense_rules: List[ExpenseCategoryRule] = field(default_factory=list)
    column_mapping: Dict[str, int] = field(default_factory=dict)
    
    # 白名单前缀 - 用于识别应收应付类科目
    allow_prefixes: List[str] = field(default_factory=lambda: ["1122", "1123", "2202", "2203"])
    
    # 默认分类
    default_income_category: str = "其他收入"
    default_expense_category: str = "管理费用_其他"
    
    _keyword_cache: Dict[str, str] = field(default_factory=dict, repr=False)
    _income_cache: Dict[str, str] = field(default_factory=dict, repr=False)
    _cache_built: bool = False
    
    def __post_init__(self):
        if not self._cache_built:
            self._build_cache()
    
    def _build_cache(self):
        """构建关键词索引缓存"""
        self._keyword_cache = {}
        self._income_cache = {}
        
        for rule in self.expense_rules:
            if not rule.category:
                continue
            for cr in rule.contra_rules:
                for kw in cr.keywords:
                    if kw:
                        self._keyword_cache[kw.lower()] = rule.category
            for kw in rule.summary_keywords:
                if kw:
                    self._keyword_cache[kw.lower()] = rule.category
        
        for rule in self.income_rules:
            if not rule.category:
                continue
            for cr in rule.contra_rules:
                for kw in cr.keywords:
                    if kw:
                        self._income_cache[kw.lower()] = rule.category
            for kw in rule.summary_keywords:
                if kw:
                    self._income_cache[kw.lower()] = rule.category
        
        self._cache_built = True
        
        print(f"📊 支出缓存: {len(self._keyword_cache)} 条关键词映射")
        print(f"📊 收入缓存: {len(self._income_cache)} 条关键词映射")
    
    def get_category_by_contra(self, contra_subject: str, summary: str = "", is_income: bool = False) -> Optional[str]:
        """根据对方科目和摘要匹配分类"""
        if not contra_subject and not summary:
            return None
    
        if not self._cache_built:
            self._build_cache()
    
        contra_lower = contra_subject.lower() if contra_subject else ""
        summary_lower = summary.lower() if summary else ""
    
        if is_income:
            if summary_lower:
                for kw, category in self._income_cache.items():
                    if kw in summary_lower:
                        return category
            if contra_lower:
                for kw, category in self._income_cache.items():
                    if kw in contra_lower:
                        return category
            return self.default_income_category
    
        if summary_lower:
            for kw, category in self._keyword_cache.items():
                if kw in summary_lower:
                    return category
        if contra_lower:
            for kw, category in self._keyword_cache.items():
                if kw in contra_lower:
                    return category
    
        return None 
    
    def should_fill_contra(self, contra_subject: str, summary: str = "") -> bool:
        """判断是否应该填充客户/供应商列（白名单模式）"""
        if not contra_subject:
            return False
        
        contra_subject = str(contra_subject)
        
        for prefix in self.allow_prefixes:
            if contra_subject.startswith(prefix):
                return True
        
        return False
    
    def rebuild_cache(self):
        self._cache_built = False
        self._build_cache()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ClassificationConfig':
        if not data:
            return cls()
        
        income_rules = []
        for rule_data in data.get('income_rules', []):
            contra_rules = []
            if 'contra_rules' in rule_data:
                for cr in rule_data.get('contra_rules', []):
                    contra_rules.append(ContraSubjectRule(
                        keywords=cr.get('keywords', []),
                        target_category=cr.get('target_category', ''),
                        description=cr.get('description', ''),
                        fuzzy=cr.get('fuzzy', False)
                    ))
            elif 'contra_keywords' in rule_data:
                contra_rules.append(ContraSubjectRule(
                    keywords=rule_data.get('contra_keywords', []),
                    target_category='',
                    description='',
                    fuzzy=False
                ))
            
            income_rules.append(IncomeCategoryRule(
                category=rule_data.get('category', ''),
                contra_rules=contra_rules,
                summary_keywords=rule_data.get('summary_keywords', []),
                description=rule_data.get('description', '')
            ))
        
        expense_rules = []
        for rule_data in data.get('expense_rules', []):
            contra_rules = []
            if 'contra_rules' in rule_data:
                for cr in rule_data.get('contra_rules', []):
                    contra_rules.append(ContraSubjectRule(
                        keywords=cr.get('keywords', []),
                        target_category=cr.get('target_category', ''),
                        description=cr.get('description', ''),
                        fuzzy=cr.get('fuzzy', False)
                    ))
            elif 'contra_keywords' in rule_data:
                contra_rules.append(ContraSubjectRule(
                    keywords=rule_data.get('contra_keywords', []),
                    target_category='',
                    description='',
                    fuzzy=False
                ))
            
            expense_rules.append(ExpenseCategoryRule(
                category=rule_data.get('category', ''),
                contra_rules=contra_rules,
                summary_keywords=rule_data.get('summary_keywords', []),
                description=rule_data.get('description', '')
            ))
        
        allow_prefixes = data.get('allow_prefixes', ["1122", "1123", "2202", "2203"])
        
        config = cls(
            income_rules=income_rules,
            expense_rules=expense_rules,
            column_mapping=data.get('column_mapping', {}),
            allow_prefixes=allow_prefixes
        )
        config._build_cache()
        
        print(f"✅ 加载了 {len(income_rules)} 条收入规则")
        print(f"✅ 加载了 {len(expense_rules)} 条支出规则")
        print(f"✅ 白名单前缀: {allow_prefixes}")
        
        return config


@dataclass
class FileConfig:
    """文件配置"""
    input_dir: str = "input"
    output_dir: str = "output"
    template_dir: str = "templates"
    log_dir: str = "logs"
    
    detail_filename: str = "明细账.xlsx"
    template_filename: str = "现金流原始表.xlsx"
    output_filename: str = "现金流_输出.xlsx"
    
    detail_files: List[str] = field(default_factory=list)
    detail_sheet_patterns: List[str] = field(default_factory=lambda: ["明细账#*", "*明细*"])
    supported_extensions: List[str] = field(default_factory=lambda: ['.xlsx', '.xls', '.xlsm'])
    
    def get_input_path(self, filename: str = None) -> Path:
        base_dir = Path(__file__).parent.parent
        input_dir = base_dir / self.input_dir
        input_dir.mkdir(parents=True, exist_ok=True)
        if filename:
            return input_dir / filename
        return input_dir / self.detail_filename
    
    def get_output_path(self, filename: str = None) -> Path:
        base_dir = Path(__file__).parent.parent
        output_dir = base_dir / self.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        if filename:
            return output_dir / filename
        return output_dir / self.output_filename
    
    def get_template_path(self) -> Path:
        base_dir = Path(__file__).parent.parent
        template_dir = base_dir / self.template_dir
        template_dir.mkdir(parents=True, exist_ok=True)
        return template_dir / self.template_filename


@dataclass
class DataConfig:
    """数据配置"""
    skip_vouchers: tuple = ("期初余额", "本期合计", "本年累计", "")
    date_column: str = "日期"
    voucher_column: str = "凭证字号"
    desc_column: str = "摘要"
    debit_column: str = "借方"
    credit_column: str = "贷方"
    contra_column: str = "对方科目"
    direction_column: str = "方向"
    balance_column: str = "余额"
    sheet_name_column: str = "_sheet_name"
    header_rows: int = 4
    report_year: int = 2026
    decimal_places: int = 2
    validation_threshold: float = 0.01
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)


@dataclass
class LogConfig:
    """日志配置"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


@dataclass
class UIConfig:
    """UI配置"""
    month_options: List[str] = field(default_factory=lambda: [
        "1月", "2月", "3月", "4月", "5月", "6月", 
        "7月", "8月", "9月", "10月", "11月", "12月"
    ])
    window_min_width: int = 1100
    window_min_height: int = 680
    color_tab_selected: str = "#4f46e5"
    global_font_family: str = "Microsoft YaHei"
    global_font_size: int = 10


class Config:
    """全局配置单例"""
    _instance: Optional['Config'] = None
    _environment: Environment = Environment.DEVELOPMENT
    
    def __new__(cls, environment: Environment = Environment.DEVELOPMENT):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._environment = environment
        return cls._instance
    
    def __init__(self, environment: Environment = Environment.DEVELOPMENT):
        if self._initialized:
            return
        self._environment = environment
        self._load_environment_config()
        self._load_classification_from_yaml()
        self._load_ui_config()
        self._initialized = True
    
    def _load_environment_config(self):
        self.file = FileConfig()
        self.data = DataConfig()
        self.log = LogConfig()
        
        if self._environment == Environment.PRODUCTION:
            self.log.level = "WARNING"
        elif self._environment == Environment.TESTING:
            self.log.level = "DEBUG"
            self.file.output_dir = "test_output"
    
    def _load_ui_config(self):
        self.ui = UIConfig()
    
    def _load_classification_from_yaml(self):
        config_path = Path(__file__).parent.parent / 'config.yaml'
        if not config_path.exists():
            print("⚠️ config.yaml 不存在，使用默认配置")
            self.data.classification = ClassificationConfig()
            return
    
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f) or {}
        
            print("=" * 60)
            print("📂 从 config.yaml 加载分类规则")
            print("=" * 60)
        
            classification_dict = {
                'income_rules': yaml_config.get('income_rules', []),
                'expense_rules': yaml_config.get('expense_rules', []),
                'column_mapping': yaml_config.get('column_mapping', {}),
                'allow_prefixes': yaml_config.get('allow_prefixes', ["1122", "1123", "2202", "2203"])
            }
        
            self.data.classification = ClassificationConfig.from_dict(classification_dict)
            print("=" * 60)
        
        except Exception as e:
            print(f"⚠️ 加载分类配置失败: {e}")
            self.data.classification = ClassificationConfig()
    
    def reload_classification(self):
        self._load_classification_from_yaml()
        if hasattr(self.data, 'classification'):
            self.data.classification.rebuild_cache()
    
    @classmethod
    def get_instance(cls, environment: Environment = Environment.DEVELOPMENT) -> 'Config':
        if cls._instance is None:
            cls._instance = Config(environment)
        return cls._instance
    
    def reset_instance(self):
        Config._instance = None
        self._initialized = False