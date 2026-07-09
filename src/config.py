# src/config.py
"""配置管理模块 - 适配新模板，支持从YAML加载分类规则"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum
import yaml


class Environment(Enum):
    """环境枚举"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class QuarterMappingStrategy(Enum):
    """季度映射策略"""
    BY_DATE = "by_date"
    BY_MONTH_MAPPING = "by_month_mapping"
    BY_VOUCHER_PREFIX = "by_voucher_prefix"
    BY_SHEET_NAME = "by_sheet_name"
    CUSTOM_RULE = "custom_rule"


@dataclass
class MonthMappingRule:
    month: int
    target_quarter: str
    description: str = ""


@dataclass
class VoucherPrefixRule:
    prefix: str
    target_quarter: str
    description: str = ""


@dataclass
class SheetNameRule:
    keyword: str
    target_quarter: str
    description: str = ""


@dataclass
class QuarterMappingConfig:
    strategy: QuarterMappingStrategy = QuarterMappingStrategy.BY_DATE
    month_mapping: Dict[int, str] = field(default_factory=lambda: {
        1: "Q1", 2: "Q1", 3: "Q1",
        4: "Q2", 5: "Q2", 6: "Q2",
        7: "Q3", 8: "Q3", 9: "Q3",
        10: "Q4", 11: "Q4", 12: "Q4"
    })
    month_rules: List[MonthMappingRule] = field(default_factory=list)
    voucher_rules: List[VoucherPrefixRule] = field(default_factory=list)
    sheet_rules: List[SheetNameRule] = field(default_factory=list)
    default_quarter: str = "Q2"
    fuzzy_match: bool = False


@dataclass
class ContraSubjectRule:
    keywords: List[str] = field(default_factory=list)
    target_category: str = ""
    description: str = ""
    fuzzy: bool = False


@dataclass
class IncomeCategoryRule:
    category: str = ""
    contra_rules: List[ContraSubjectRule] = field(default_factory=list)
    summary_keywords: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ExpenseCategoryRule:
    category: str = ""
    contra_rules: List[ContraSubjectRule] = field(default_factory=list)
    summary_keywords: List[str] = field(default_factory=list)
    description: str = ""


# src/config.py - 修复 ClassificationConfig

@dataclass
class ClassificationConfig:
    """分类配置 - 支持从YAML加载，带预编译缓存"""
    income_rules: List[IncomeCategoryRule] = field(default_factory=list)
    expense_rules: List[ExpenseCategoryRule] = field(default_factory=list)
    column_mapping: Dict[str, int] = field(default_factory=dict)
    
    # ===== 白名单前缀 =====
    allow_prefixes: List[str] = field(default_factory=lambda: ["1122", "1123", "2202", "2203"])
    
    # 保留但不使用的字段（向后兼容）
    exclude_keywords: List[str] = field(default_factory=list)
    
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
        
        # ===== 从 expense_rules 构建支出缓存 =====
        for rule in self.expense_rules:
            if not rule.category:
                continue
            # 从 contra_rules 中提取关键词
            for cr in rule.contra_rules:
                for kw in cr.keywords:
                    if kw:
                        self._keyword_cache[kw.lower()] = rule.category
            # 从 summary_keywords 中提取关键词
            for kw in rule.summary_keywords:
                if kw:
                    self._keyword_cache[kw.lower()] = rule.category
        
        # ===== 从 income_rules 构建收入缓存 =====
        for rule in self.income_rules:
            if not rule.category:
                continue
            # 从 contra_rules 中提取关键词
            for cr in rule.contra_rules:
                for kw in cr.keywords:
                    if kw:
                        self._income_cache[kw.lower()] = rule.category
            # 从 summary_keywords 中提取关键词
            for kw in rule.summary_keywords:
                if kw:
                    self._income_cache[kw.lower()] = rule.category
        
        self._cache_built = True
        
        # 打印缓存构建信息
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
    
        # ===== 收入匹配 =====
        if is_income:
            # 优先匹配摘要
            if summary_lower:
                for kw, category in self._income_cache.items():
                    if kw in summary_lower:
                        return category
            # 再匹配对方科目
            if contra_lower:
                for kw, category in self._income_cache.items():
                    if kw in contra_lower:
                        return category
            # ===== 所有收入都归入"其他收入" =====
            return "其他收入"
    
        # ===== 支出匹配 =====
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
    
    def should_exclude_contra(self, contra_subject: str, summary: str = "") -> bool:
        """判断是否应该排除（不填充客户/供应商列）"""
        return not self.should_fill_contra(contra_subject, summary)
    
    def rebuild_cache(self):
        self._cache_built = False
        self._build_cache()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ClassificationConfig':
        if not data:
            return cls()
        
        # ===== 解析收入规则 =====
        income_rules = []
        for rule_data in data.get('income_rules', []):
            contra_rules = []
            # 支持两种格式：contra_rules 或 contra_keywords
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
        
        # ===== 解析支出规则 =====
        expense_rules = []
        for rule_data in data.get('expense_rules', []):
            contra_rules = []
            # 支持两种格式：contra_rules 或 contra_keywords
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
        
        # ===== 读取白名单前缀 =====
        allow_prefixes = data.get('allow_prefixes', ["1122", "1123", "2202", "2203"])
        
        # ===== 读取排除关键词（保留但不再使用） =====
        exclude_keywords = data.get('exclude_keywords', [])
        if not exclude_keywords and 'contra_filter' in data:
            exclude_keywords = data.get('contra_filter', {}).get('exclude_keywords', [])
        
        config = cls(
            income_rules=income_rules,
            expense_rules=expense_rules,
            column_mapping=data.get('column_mapping', {}),
            exclude_keywords=exclude_keywords,
            allow_prefixes=allow_prefixes
        )
        config._build_cache()
        
        # 打印加载信息
        print(f"✅ 加载了 {len(income_rules)} 条收入规则")
        print(f"✅ 加载了 {len(expense_rules)} 条支出规则")
        print(f"✅ 白名单前缀: {allow_prefixes}")
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        def rules_to_dict(rules):
            result = []
            for rule in rules:
                item = {
                    'category': rule.category,
                    'contra_rules': [
                        {
                            'keywords': cr.keywords,
                            'target_category': cr.target_category,
                            'description': cr.description,
                            'fuzzy': cr.fuzzy
                        }
                        for cr in rule.contra_rules
                    ],
                    'summary_keywords': rule.summary_keywords,
                    'description': rule.description
                }
                result.append(item)
            return result
        
        return {
            'income_rules': rules_to_dict(self.income_rules),
            'expense_rules': rules_to_dict(self.expense_rules),
            'column_mapping': self.column_mapping,
            'allow_prefixes': self.allow_prefixes,
            'exclude_keywords': self.exclude_keywords
        }


@dataclass
class FileConfig:
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
    quarter_names: List[str] = field(default_factory=lambda: ["Q1", "Q2", "Q3", "Q4"])
    decimal_places: int = 2
    validation_threshold: float = 0.01
    quarter_mapping: QuarterMappingConfig = field(default_factory=QuarterMappingConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)


@dataclass
class LogConfig:
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


@dataclass
class UIConfig:
    quarter_options: List[str] = field(default_factory=lambda: ["Q1", "Q2", "Q3", "Q4"])
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
            # 设置默认白名单
            self.data.classification = ClassificationConfig()
            self.data.classification.allow_prefixes = ["1122", "1123", "2202", "2203"]
            return
    
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f) or {}
        
            print("=" * 60)
            print("📂 从 config.yaml 加载分类规则")
            print("=" * 60)
        
            income_rules_data = yaml_config.get('income_rules', [])
            expense_rules_data = yaml_config.get('expense_rules', [])
            column_mapping = yaml_config.get('column_mapping', {})
            
            # ===== 读取白名单前缀 =====
            allow_prefixes = yaml_config.get('allow_prefixes', ["1122", "1123", "2202", "2203"])
        
            print(f"📊 收入规则: {len(income_rules_data)} 条")
            print(f"📊 支出规则: {len(expense_rules_data)} 条")
        
            if expense_rules_data:
                print("📋 支出规则:")
                for i, rule in enumerate(expense_rules_data):
                    category = rule.get('category', '未知')
                    keywords = rule.get('contra_keywords', [])
                    print(f"  {i+1}. {category}: {keywords}")
            else:
                print("📋 支出规则: (无)")
        
            print(f"✅ 白名单前缀: {allow_prefixes}")
            print(f"💡 只有对方科目以 {allow_prefixes} 开头的交易才会填充客户/供应商列")
            print("=" * 60)
        
            classification_dict = {
                'income_rules': income_rules_data,
                'expense_rules': expense_rules_data,
                'column_mapping': column_mapping,
                'allow_prefixes': allow_prefixes
            }
        
            self.data.classification = ClassificationConfig.from_dict(classification_dict)
        
        except Exception as e:
            print(f"⚠️ 加载分类配置失败: {e}")
            self.data.classification = ClassificationConfig()
            self.data.classification.allow_prefixes = ["1122", "1123", "2202", "2203"]
    
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