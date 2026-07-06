# src/strategies/default_strategy.py
"""默认分类规则配置"""

DEFAULT_CLASSIFICATION_RULES = {
    # 主营业务支出
    "商品采购": {
        "keywords": ["商品采购", "采购", "货款", "采购款"],
        "contra_prefixes": ["2202"],
        "exclude": ["服务", "运费", "返点"],
        "is_income": False
    },
    "运费": {
        "keywords": ["运费", "快递", "物流", "运输", "闪送", "顺丰", "啦啦"],
        "contra_prefixes": [],
        "exclude": [],
        "is_income": False
    },
    "服务费": {
        "keywords": ["服务费", "检测", "报告费", "专利申请", "网站年费"],
        "contra_prefixes": [],
        "exclude": [],
        "is_income": False
    },
    "返点佣金": {
        "keywords": ["返点", "佣金", "经销返点"],
        "contra_prefixes": [],
        "exclude": [],
        "is_income": False
    },
    
    # 管理费用
    "管理_人员薪资": {
        "keywords": ["工资", "薪资", "奖金", "发放工资"],
        "contra_prefixes": ["221101"],
        "exclude": [],
        "is_income": False
    },
    "管理_社保公积金": {
        "keywords": ["社保", "公积金", "缴公积金"],
        "contra_prefixes": ["221103"],
        "exclude": [],
        "is_income": False
    },
    "管理_租金物业": {
        "keywords": ["房租", "物业", "水电", "飞雕国际", "租金"],
        "contra_prefixes": [],
        "exclude": [],
        "is_income": False
    },
    "管理_员工福利": {
        "keywords": ["福利", "团建", "聚餐", "福利费"],
        "contra_prefixes": ["560202"],
        "exclude": [],
        "is_income": False
    },
    "管理_办公费": {
        "keywords": ["办公", "文具", "打印", "耗材", "软件"],
        "contra_prefixes": [],
        "exclude": ["租金", "物业", "房租"],
        "is_income": False
    },
    "管理_通讯费": {
        "keywords": ["通讯费", "电话费", "网络费"],
        "contra_prefixes": ["560208"],
        "exclude": [],
        "is_income": False
    },
    "管理_招待费": {
        "keywords": ["管理招待", "管理餐费"],
        "contra_prefixes": [],
        "exclude": ["销售"],
        "is_income": False
    },
    "管理_其他": {
        "keywords": ["报销"],
        "contra_prefixes": ["224105", "224106"],
        "exclude": [],
        "is_income": False
    },
    
    # 销售费用
    "销售_招待费": {
        "keywords": ["招待", "餐费", "客户招待"],
        "contra_prefixes": ["560104"],
        "exclude": ["管理"],
        "is_income": False
    },
    "销售_交通费": {
        "keywords": ["飞机", "动车", "高铁", "火车", "车票"],
        "contra_prefixes": [],
        "exclude": ["市内", "管理"],
        "is_income": False
    },
    "销售_市内交通": {
        "keywords": ["打车", "出租车", "滴滴", "地铁", "公交", "市内交通"],
        "contra_prefixes": [],
        "exclude": [],
        "is_income": False
    },
    
    # 财务费用
    "财务_手续费": {
        "keywords": ["手续费", "银行手续费"],
        "contra_prefixes": [],
        "exclude": [],
        "is_income": False
    },
    "财务_结息": {
        "keywords": ["结息", "利息收入"],
        "contra_prefixes": [],
        "exclude": [],
        "is_income": False
    },
    
    # 税金
    "税金_个税": {
        "keywords": ["个人所得税", "个税"],
        "contra_prefixes": ["222112"],
        "exclude": [],
        "is_income": False
    },
    
    # 收入类
    "产品收入": {
        "keywords": ["产品收入", "商品销售", "电脑及配件"],
        "contra_prefixes": ["112201"],
        "exclude": [],
        "is_income": True
    },
    "服务收入": {
        "keywords": ["服务收入", "技术服务", "咨询"],
        "contra_prefixes": [],
        "exclude": [],
        "is_income": True
    },
    "其他收入": {
        "keywords": ["其他收入", "零星收入", "收客户款"],
        "contra_prefixes": [],
        "exclude": [],
        "is_income": True
    }
}