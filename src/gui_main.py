"""现金流量报表生成器 - 简洁版GUI"""

import sys
import yaml
import logging
import traceback
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from config import Config, Environment

# ==================== 日志配置 ====================
LOG_FILE = PROJECT_ROOT / 'logs' / 'app.log'
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('CashFlowGenerator')


class ConfigManager:
    """配置管理器 - 只负责读写 config.yaml"""
    
    def __init__(self):
        self.config_path = PROJECT_ROOT / 'config.yaml'
        self.config = {}
        self._load_config()
    
    def _load_config(self):
        """从文件加载配置"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"加载配置失败: {e}")
                self.config = {}
        return self.config
    
    def save_config(self, config):
        """保存配置到文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            self.config = config
            logger.info("配置已保存")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            raise


class WorkerThread(QThread):
    """后台工作线程 - 纯串行版"""
    progress_updated = pyqtSignal(int, str)
    log_updated = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, detail_path, bank_name, period_display, quarter, 
                 sheet_name, cashflow_file):
        super().__init__()
        self.detail_path = detail_path
        self.bank_name = bank_name
        self.period_display = period_display
        self.quarter = quarter
        self.sheet_name = sheet_name
        self.cashflow_file = cashflow_file
        self._is_running = True
        self._start_time = None
    
    def stop(self):
        self._is_running = False
    
    def run(self):
        import time
        self._start_time = time.time()
    
        try:
            from main import CashFlowReportGenerator
        
            self.progress_updated.emit(5, "初始化...")
            self.log_updated.emit('▶ 开始运行')
        
            config_obj = Config.get_instance(Environment.DEVELOPMENT)
            config_obj.reload_classification()
        
            if self.cashflow_file:
                config_obj.file.output_dir = str(self.cashflow_file.parent)
                self.log_updated.emit(f'📂 输出目录: {self.cashflow_file.parent}')
        
            # ===== 打印当前生效的规则 =====
            classification = config_obj.data.classification
            expense_rules = classification.expense_rules
            exclude_keywords = classification.exclude_keywords
            
            self.log_updated.emit(f'📋 当前生效的支出规则: {len(expense_rules)} 条')
            for rule in expense_rules:
                keywords = []
                for cr in rule.contra_rules:
                    keywords.extend(cr.keywords)
                if keywords:
                    self.log_updated.emit(f'  - {rule.category}: {keywords}')
            
            self.log_updated.emit(f'🚫 当前生效的排除关键词: {len(exclude_keywords)} 条')
            for kw in exclude_keywords:
                self.log_updated.emit(f'  - {kw}')
        
            self.progress_updated.emit(10, "加载数据...")
            self.log_updated.emit(f'📊 加载明细账...')
        
            generator = CashFlowReportGenerator(Environment.DEVELOPMENT)
            generator.bank_name = self.bank_name
            generator.period_value = self.period_display
            generator.sheet_name = self.sheet_name
            generator.output_filename = self.cashflow_file.name
        
            generator.set_output_path(self.cashflow_file)
        
            self.log_updated.emit('📂 开始加载交易数据...')
            transactions = generator.load_transactions(self.detail_path)
            self.log_updated.emit(f'📊 加载完成，共 {len(transactions)} 笔')
        
            if not self._is_running:
                self.finished.emit(False, "已停止")
                return
        
            self.progress_updated.emit(40, f"加载完成 ({len(transactions)}笔)")
            self.log_updated.emit(f'✅ 加载 {len(transactions)} 笔交易')
        
            if len(transactions) == 0:
                self.finished.emit(False, "没有找到交易数据")
                return
        
            self.progress_updated.emit(50, "分类聚合中...")
            self.log_updated.emit('📝 串行分类处理...')
        
            generator.transactions = transactions
        
            self.log_updated.emit('🔄 开始执行 run_full_flow...')
            success = generator.run_full_flow(self.detail_path, self.quarter)
            self.log_updated.emit(f'🔄 run_full_flow 返回: {success}')
        
            if not self._is_running:
                self.finished.emit(False, "已停止")
                return
        
            if not success:
                self.finished.emit(False, "生成失败")
                return
        
            elapsed = time.time() - self._start_time
            self.progress_updated.emit(100, "完成!")
            self.log_updated.emit(f'✅ 报表已生成: {generator.output_path}')
            self.log_updated.emit(f'⏱️ 总耗时: {elapsed:.1f} 秒')
        
            self.finished.emit(True, str(generator.output_path))
        
        except Exception as e:
            import traceback
            error_msg = str(e)
            error_detail = traceback.format_exc()
            self.log_updated.emit(f'❌ 错误: {error_msg}')
            self.log_updated.emit(f'📋 详细错误:\n{error_detail}')
            logger.error(f"生成失败: {error_msg}\n{error_detail}")
            self.finished.emit(False, error_msg)


class MainWindow(QMainWindow):
    """主窗口 - 简洁版"""
    
    # 统一按钮尺寸
    BTN_WIDTH = 100
    BTN_HEIGHT = 32
    BTN_RADIUS = 6
    BTN_FONT_SIZE = 13
    
    def __init__(self):
        super().__init__()
        
        self.settings = QSettings('Weiyu', 'CashFlowGenerator')
        
        # 使用 Config 单例
        self.config_obj = Config.get_instance(Environment.DEVELOPMENT)
        self.config_obj.reload_classification()
        
        # ConfigManager 负责读写 yaml 文件
        self.config_manager = ConfigManager()
        
        self.worker_thread = None
        self.recent_files = self.settings.value('recent_files', []) or []
        
        self.ui_config = self.config_obj.ui
        
        self.init_ui()
        self.load_config()
        self.restore_window()
        self.update_recent_menu()
    
    # ==================== 窗口管理 ====================
    def restore_window(self):
        geo = self.settings.value('window_geometry')
        if geo:
            self.restoreGeometry(geo)
    
    def save_window(self):
        self.settings.setValue('window_geometry', self.saveGeometry())
    
    def closeEvent(self, event):
        self.save_window()
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.worker_thread.wait()
        super().closeEvent(event)
    
    # ==================== 菜单栏 ====================
    def create_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu('文件(&F)')
        
        self.recent_menu = QMenu('最近文件(&R)', self)
        file_menu.addMenu(self.recent_menu)
        
        file_menu.addSeparator()
        
        save_action = QAction('保存配置(&S)', self)
        save_action.setShortcut('Ctrl+S')
        save_action.triggered.connect(self.save_config)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('退出(&X)', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        tools_menu = menubar.addMenu('工具(&T)')
        
        preview_action = QAction('数据预览(&P)', self)
        preview_action.setShortcut('Ctrl+P')
        preview_action.triggered.connect(self.preview_data)
        tools_menu.addAction(preview_action)
        
        validate_action = QAction('验证规则(&V)', self)
        validate_action.triggered.connect(self.validate_rules)
        tools_menu.addAction(validate_action)
        
        help_menu = menubar.addMenu('帮助(&H)')
        about_action = QAction('关于(&A)', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def update_recent_menu(self):
        self.recent_menu.clear()
        if not self.recent_files:
            no_action = QAction('(无最近文件)', self)
            no_action.setEnabled(False)
            self.recent_menu.addAction(no_action)
            return
        
        for path in self.recent_files[:10]:
            action = QAction(Path(path).name, self)
            action.setToolTip(path)
            action.triggered.connect(lambda checked, p=path: self.open_recent(p))
            self.recent_menu.addAction(action)
        
        self.recent_menu.addSeparator()
        clear_action = QAction('清空列表', self)
        clear_action.triggered.connect(self.clear_recent)
        self.recent_menu.addAction(clear_action)
    
    def open_recent(self, path):
        if Path(path).exists():
            self.detail_path.setText(path)
            self.detail_path.setStyleSheet('background: white; color: #1e293b;')
            self.append_log(f'📁 打开: {Path(path).name}')
            self.auto_save()
        else:
            self.recent_files.remove(path)
            self.update_recent_menu()
    
    def clear_recent(self):
        self.recent_files = []
        self.settings.setValue('recent_files', self.recent_files)
        self.update_recent_menu()
    
    def add_recent(self, path):
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:10]
        self.settings.setValue('recent_files', self.recent_files)
        self.update_recent_menu()
    
    def validate_rules(self):
        """验证规则格式是否正确（用户主动点击验证按钮）"""
        is_valid, errors = self._check_rules()
    
        if is_valid:
            QMessageBox.information(self, '验证通过', '✅ 规则格式正确')
            return True
        else:
            # 构建错误信息，包含行号和原始内容
            error_msg = "支出规则存在以下语法错误：\n\n"
            for err in errors:
                error_msg += f"  • {err}\n"
            error_msg += "\n💡 请根据提示修正后重新验证"
        
            QMessageBox.warning(self, '规则错误', error_msg)
            return False 
    
    def preview_data(self):
        path = self.detail_path.text().strip()
        if not path or not Path(path).exists():
            QMessageBox.warning(self, '提示', '请先选择明细账文件')
            return
        
        try:
            from services.data_loader import DataLoader
            loader = DataLoader(Config.get_instance())
            transactions = loader.load_from_files([path])
            
            if not transactions:
                QMessageBox.warning(self, '提示', '没有交易数据')
                return
            
            dialog = QDialog(self)
            dialog.setWindowTitle(f'数据预览 ({len(transactions)}笔)')
            dialog.resize(850, 500)
            
            layout = QVBoxLayout(dialog)
            
            info = QLabel(f'总计 {len(transactions)} 笔 | 收入 {len([t for t in transactions if t.is_income])} 笔 | 支出 {len([t for t in transactions if not t.is_income])} 笔')
            layout.addWidget(info)
            
            table = QTableWidget()
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(['日期', '摘要', '对方科目', '金额', '类型'])
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            table.setAlternatingRowColors(True)
            
            show = min(len(transactions), 200)
            table.setRowCount(show)
            for i, t in enumerate(transactions[:show]):
                table.setItem(i, 0, QTableWidgetItem(t.date.strftime('%Y-%m-%d') if t.date else ''))
                table.setItem(i, 1, QTableWidgetItem(t.description[:25] if hasattr(t, 'description') else ''))
                table.setItem(i, 2, QTableWidgetItem(t.contra_subject[:20] if hasattr(t, 'contra_subject') else ''))
                table.setItem(i, 3, QTableWidgetItem(f"{float(t.amount):,.2f}"))
                table.setItem(i, 4, QTableWidgetItem('收入' if t.is_income else '支出'))
            
            layout.addWidget(table)
            
            if len(transactions) > 200:
                layout.addWidget(QLabel(f'⚠️ 仅显示前200笔'))
            
            btn = QPushButton('关闭')
            btn.clicked.connect(dialog.accept)
            layout.addWidget(btn, alignment=Qt.AlignRight)
            
            dialog.exec_()
            
        except Exception as e:
            QMessageBox.critical(self, '错误', f'预览失败: {e}')
    
    def _log_rules(self):
        """在日志中展示当前规则（程序内部格式）"""
        classification = self.config_obj.data.classification
        expense_rules = classification.expense_rules
        exclude_keywords = classification.exclude_keywords
    
        self.append_log('')
        self.append_log('=' * 60)
        self.append_log('📋 当前加载的支出规则:')
        if expense_rules:
            for rule in expense_rules:
                keywords = []
                for cr in rule.contra_rules:
                    keywords.extend(cr.keywords)
                keywords.extend(rule.summary_keywords)
                if keywords:
                    self.append_log(f'  {rule.category}: {keywords}')
        else:
            self.append_log('  (无支出规则)')
    
        self.append_log('')
        self.append_log('🚫 当前加载的排除关键词:')
        if exclude_keywords:
            self.append_log(f'  {exclude_keywords}')
        else:
            self.append_log('  (无排除关键词)')
        self.append_log('=' * 60)
        self.append_log('')
    def save_config(self):
        try:
            config = self.build_config()
            self.config_manager.save_config(config)
            self.config_obj.reload_classification()
        
            # ===== 在日志中展示保存的规则 =====
            self._log_rules()
        
            self.append_log('💾 配置已保存并重新加载')
            QMessageBox.information(self, '完成', '配置已保存并生效')
        except Exception as e:
            QMessageBox.critical(self, '错误', f'保存失败: {e}') 
    
    def show_about(self):
        QMessageBox.about(self, '关于', 
            '📊 现金流量报表生成器\n\n'
            '版本 1.0\n\n'
            '根据明细账自动生成现金流量报表\n\n'
            '快捷键:\n'
            '  Ctrl+P  数据预览\n'
            '  Ctrl+R  运行\n'
            '  Ctrl+S  保存配置'
        )
    
    # ==================== UI ====================
    def init_ui(self):
        self.setWindowTitle('现金流量报表生成器')
        self.setMinimumSize(1100, 680)
        self.resize(1100, 680)
        
        font = QFont("Microsoft YaHei", 10)
        QApplication.setFont(font)
        
        self.setStyleSheet(self._get_style())
        self.create_menu_bar()
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(14)
        layout.setContentsMargins(30, 14, 30, 20)
        
        # 标题
        title = QLabel('📊 现金流量报表生成器')
        title.setStyleSheet('font-size: 24px; font-weight: bold; color: #0f172a; padding: 6px 0 12px 0;')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Tab
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        self.tabs.addTab(self.create_basic_tab(), '📋 基本设置')
        self.tabs.addTab(self.create_rules_tab(), '📌 支出规则')
        self.tabs.addTab(self.create_exclude_tab(), '🚫 不填充规则')
        self.tabs.addTab(self.create_log_tab(), '📝 日志')
        
        # ===== 底部区域 =====
        bottom_widget = QWidget()
        bottom_widget.setStyleSheet("""
            QWidget {
                background: white;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(16, 8, 16, 8)
        bottom_layout.setSpacing(16)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat('%p%')
        self.progress_bar.setFixedHeight(32)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 6px;
                background: #f1f5f9;
                text-align: center;
                font-weight: 600;
                font-size: 13px;
                color: #1e293b;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4f46e5, stop:1 #059669);
                border-radius: 6px;
            }
        """)
        bottom_layout.addWidget(self.progress_bar, 1)
        
        self.progress_label = QLabel('就绪')
        self.progress_label.setFixedWidth(80)
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet("""
            QLabel {
                color: #64748b;
                font-size: 13px;
                font-weight: 500;
                background: transparent;
                border: none;
            }
        """)
        bottom_layout.addWidget(self.progress_label)
        
        self.run_btn = self._create_button('▶ 运行', '#059669', '#047857', '#94a3b8')
        self.run_btn.clicked.connect(self.run_generator)
        bottom_layout.addWidget(self.run_btn)

        self.stop_btn = self._create_button('⏹ 停止', '#dc2626', '#b91c1c', '#cbd5e1')
        self.stop_btn.clicked.connect(self.stop_generator)
        self.stop_btn.setEnabled(False)
        bottom_layout.addWidget(self.stop_btn)
        
        layout.addWidget(bottom_widget)
        
        # 快捷键
        QShortcut(QKeySequence('Ctrl+P'), self, self.preview_data)
        QShortcut(QKeySequence('Ctrl+R'), self, self.run_generator)
        QShortcut(QKeySequence('Ctrl+S'), self, self.save_config)
    
    def _create_button(self, text, bg_color, hover_color, disabled_color):
        btn = QPushButton(text)
        btn.setFixedSize(self.BTN_WIDTH, self.BTN_HEIGHT)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                color: white;
                border: none;
                border-radius: {self.BTN_RADIUS}px;
                font-weight: 600;
                font-size: {self.BTN_FONT_SIZE}px;
            }}
            QPushButton:hover {{ background: {hover_color}; }}
            QPushButton:disabled {{ 
                background: {bg_color};
                opacity: 0.6;
            }}
        """)
        return btn
    
    def _get_style(self):
        return """
            QMainWindow { background: #f1f5f9; }
            
            QTabWidget::pane {
                border: 0px solid #e2e8f0;
                background: white;
                border-radius: 0 12px 12px 12px;
                padding: 6px;
                margin-top: -1px;
            }
            QTabBar::tab {
                background: #f1f5f9;
                padding: 10px 30px;
                margin-right: 2px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                font-size: 15px;
                color: #64748b;
            }
            QTabBar::tab:selected {
                background: white;
                color: #4f46e5;
                border: none;
            }
            
            QGroupBox {
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 16px;
                background: white;
            }
            QGroupBox::title {
                left: 16px;
                padding: 0 12px;
                color: #0f172a;
                font-size: 15px;
                font-weight: 600;
            }
            
            QLabel {
                color: #1e293b;
                font-size: 14px;
                min-height: 30px;
            }
            
            QLineEdit {
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 14px;
                background: white;
                min-height: 20px;
                color: #1e293b;
            }
            QLineEdit:focus { border-color: #4f46e5; }
            QLineEdit:hover { border-color: #94a3b8; }
            QLineEdit:disabled { background: #f1f5f9; color: #94a3b8; }
            QLineEdit#placeholder {
                background: #f8fafc;
                color: #94a3b8;
            }
            QLineEdit#placeholder:focus { border-color: #e2e8f0; }
            
            QTextEdit {
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                font-size: 15px;
                padding: 12px;
                background: white;
                font-family: 'Consolas', monospace;
                line-height: 1.6;
                color: #1e293b;
            }
            QTextEdit:focus { border-color: #4f46e5; }
            
            QPushButton#toolBtn {
                background: #f1f5f9;
                color: #1e293b;
                border: 1px solid #e2e8f0;
                padding: 6px 16px;
                font-size: 13px;
                border-radius: 6px;
                min-height: 30px;
            }
            QPushButton#toolBtn:hover { background: #e5e7eb; }
            
            QProgressBar {
                border: none;
                border-radius: 6px;
                background: #f1f5f9;
                text-align: center;
                font-weight: 600;
                font-size: 13px;
                color: #1e293b;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4f46e5, stop:1 #059669);
                border-radius: 6px;
            }
            
            QScrollBar:vertical {
                border: none;
                background: #f1f5f9;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #94a3b8; }
            
            QMenuBar {
                background: #f8fafc;
                border-bottom: 1px solid #e2e8f0;
            }
            QMenuBar::item {
                padding: 6px 12px;
                font-size: 14px;
            }
            QMenuBar::item:selected {
                background: #4f46e5;
                color: white;
            }
            QMenu {
                background: white;
                border: 1px solid #e2e8f0;
                padding: 6px;
            }
            QMenu::item {
                padding: 6px 30px;
                font-size: 14px;
            }
            QMenu::item:selected {
                background: #4f46e5;
                color: white;
            }
        """
    
    # ==================== Tab 创建 ====================
    def create_basic_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        layout.setContentsMargins(40, 22, 40, 22)
        
        # 报表设置
        g1 = QGroupBox('报表设置')
        g1.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 16px;
                background: white;
            }
            QGroupBox::title {
                left: 16px;
                padding: 0 12px;
                color: #0f172a;
                font-size: 15px;
                font-weight: 600;
            }
        """)
        
        grid = QGridLayout()
        grid.setVerticalSpacing(16)
        grid.setHorizontalSpacing(24)
        grid.setContentsMargins(28, 20, 28, 18)
        
        period_label = QLabel('期间：')
        period_label.setStyleSheet('font-weight: 500; color: #1e293b;')
        grid.addWidget(period_label, 0, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
        
        self.period_input = QLineEdit()
        self.period_input.setPlaceholderText('例如: Q1, Q2, 1月, 2月')
        self.period_input.setMinimumHeight(32)
        self.period_input.setFixedWidth(150)
        self.period_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 14px;
                background: white;
                min-height: 30px;
                color: #1e293b;
            }
            QLineEdit:focus { border-color: #4f46e5; }
            QLineEdit:hover { border-color: #94a3b8; }
        """)
        grid.addWidget(self.period_input, 0, 1, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        
        bank_label = QLabel('银行名称：')
        bank_label.setStyleSheet('font-weight: 500; color: #1e293b;')
        grid.addWidget(bank_label, 0, 2, alignment=Qt.AlignRight | Qt.AlignVCenter)
        
        self.bank_name = QLineEdit()
        self.bank_name.setPlaceholderText('例如: 建设银行')
        self.bank_name.setMinimumHeight(32)
        self.bank_name.setFixedWidth(180)
        self.bank_name.setStyleSheet("""
            QLineEdit {
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 14px;
                background: white;
                min-height: 30px;
                color: #1e293b;
            }
            QLineEdit:focus { border-color: #4f46e5; }
            QLineEdit:hover { border-color: #94a3b8; }
        """)
        grid.addWidget(self.bank_name, 0, 3, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)
        
        g1.setLayout(grid)
        layout.addWidget(g1)
        
        # 文件路径
        g2 = QGroupBox('文件路径')
        g2.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 16px;
                background: white;
            }
            QGroupBox::title {
                left: 16px;
                padding: 0 12px;
                color: #0f172a;
                font-size: 15px;
                font-weight: 600;
            }
        """)
        
        f2 = QFormLayout()
        f2.setVerticalSpacing(16)
        f2.setHorizontalSpacing(20)
        f2.setContentsMargins(28, 20, 28, 18)
        
        # 明细账
        detail_container = QHBoxLayout()
        detail_container.setSpacing(10)

        self.detail_path = QLineEdit()
        self.detail_path.setObjectName('placeholder')
        self.detail_path.setPlaceholderText('点击右侧按钮选择明细账文件')
        self.detail_path.setReadOnly(True)
        self.detail_path.setFixedHeight(self.BTN_HEIGHT)
        self.detail_path.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 2px 14px;
                font-size: 14px;
                background: #f8fafc;
                color: #94a3b8;
                height: {self.BTN_HEIGHT}px;
            }}
            QLineEdit:focus {{ border-color: #4f46e5; }}
        """)
        detail_container.addWidget(self.detail_path, 1)

        self.detail_btn = self._create_tool_button('📂 选择')
        self.detail_btn.clicked.connect(self.select_detail_file)
        detail_container.addWidget(self.detail_btn, 0, Qt.AlignVCenter)

        f2.addRow('明细账：', detail_container)

        # 现金流表
        cashflow_container = QHBoxLayout()
        cashflow_container.setSpacing(10)

        self.cashflow_path = QLineEdit()
        self.cashflow_path.setObjectName('placeholder')
        self.cashflow_path.setPlaceholderText('选择输出目录 或 已有现金流表文件')
        self.cashflow_path.setReadOnly(True)
        self.cashflow_path.setFixedHeight(self.BTN_HEIGHT)
        self.cashflow_path.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 2px 14px;
                font-size: 14px;
                background: #f8fafc;
                color: #94a3b8;
                height: {self.BTN_HEIGHT}px;
            }}
            QLineEdit:focus {{ border-color: #4f46e5; }}
        """)
        cashflow_container.addWidget(self.cashflow_path, 1)

        self.cashflow_btn = self._create_tool_button('📂 选择')
        self.cashflow_btn.clicked.connect(self.select_cashflow_target)
        cashflow_container.addWidget(self.cashflow_btn, 0, Qt.AlignVCenter)

        f2.addRow('现金流表：', cashflow_container)
       
        # 模式提示
        self.mode_hint = QLabel('💡 选择目录 → 自动创建 公司名_时间戳.xlsx  |  选择已有文件 → 添加Sheet')
        self.mode_hint.setStyleSheet('color: #94a3b8; font-size: 13px; padding: 4px 0 0 0;')
        f2.addRow('', self.mode_hint)
        
        g2.setLayout(f2)
        layout.addWidget(g2)
        
        layout.addStretch()
        return widget
    
    def _create_tool_button(self, text):
        btn = QPushButton(text)
        btn.setObjectName('toolBtn')
        btn.setFixedSize(self.BTN_WIDTH, self.BTN_HEIGHT)
        btn.setStyleSheet(f"""
            QPushButton#toolBtn {{
                background: #f1f5f9;
                color: #1e293b;
                border: 2px solid #e2e8f0;
                border-radius: {self.BTN_RADIUS}px;
                font-size: {self.BTN_FONT_SIZE}px;
                font-weight: 500;
                padding: 3px 8px;
                margin-top: 8px;
            }}
            QPushButton#toolBtn:hover {{ background: #e5e7eb; }}
        """)
        return btn
    
    def create_rules_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(40, 18, 40, 18)
        
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        
        validate_btn = self._create_tool_button('校验')
        validate_btn.clicked.connect(self.validate_rules)
        toolbar.addWidget(validate_btn)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        hint = QLabel('格式: 分类名称:关键词1,关键词2,关键词3  (每行一条)')
        hint.setStyleSheet('color: #94a3b8; font-size: 13px;')
        layout.addWidget(hint)
        
        self.expense_rules = QTextEdit()
        self.expense_rules.setPlaceholderText(
            '示例:\n'
            '商品采购:付供应商款,采购款,货款\n'
            '运费:运费,快递,物流,顺丰\n'
            '财务_手续费:银行手续费,手续费'
        )
        self.expense_rules.setMinimumHeight(360)
        layout.addWidget(self.expense_rules)
        
        return widget
    
    def create_exclude_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(40, 18, 40, 18)
        
        hint = QLabel('每行一个关键词，匹配到的科目不填充客户/供应商列')
        hint.setStyleSheet('color: #94a3b8; font-size: 13px;')
        layout.addWidget(hint)
        
        self.exclude_keywords = QTextEdit()
        self.exclude_keywords.setPlaceholderText(
            '应付职工薪酬\n应交税费\n管理费用\n销售费用\n财务费用\n研发费用\n固定资产\n银行存款'
        )
        self.exclude_keywords.setMinimumHeight(360)
        layout.addWidget(self.exclude_keywords)
        
        tip = QLabel('💡 应收/应付类科目会自动填充客户/供应商列')
        tip.setStyleSheet('color: #94a3b8; font-size: 13px; padding: 4px 0;')
        layout.addWidget(tip)
        
        layout.addStretch()
        return widget
    
    def create_log_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(30, 16, 30, 16)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', monospace;
                font-size: 14px;
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 18px;
                min-height: 370px;
            }
        """)
        layout.addWidget(self.log_text)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        clear_btn = self._create_tool_button('清空日志')
        clear_btn.clicked.connect(lambda: self.log_text.clear())
        btn_layout.addWidget(clear_btn)
        layout.addLayout(btn_layout)
        
        return widget
    
    # ==================== 文件选择 ====================
    def select_detail_file(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择明细账文件', '', 'Excel文件 (*.xlsx *.xls)')
        if path:
            self.detail_path.setText(path)
            self.detail_path.setStyleSheet('background: white; color: #1e293b;')
            self.add_recent(path)
            self.append_log(f'📁 明细账: {Path(path).name}')
            self.auto_save()
    
    def select_cashflow_target(self):
        msg = QMessageBox(self)
        msg.setWindowTitle('选择现金流表')
        msg.setText('请选择操作模式：')
        dir_btn = msg.addButton('📂 选择输出目录', QMessageBox.ActionRole)
        file_btn = msg.addButton('📄 选择已有文件', QMessageBox.ActionRole)
        cancel_btn = msg.addButton('取消', QMessageBox.RejectRole)
        msg.exec_()
        
        clicked = msg.clickedButton()
        
        if clicked == cancel_btn:
            return
        
        elif clicked == dir_btn:
            current = self.cashflow_path.text().strip()
            if current and Path(current).suffix in ['.xlsx', '.xls']:
                current = str(Path(current).parent)
            elif not current:
                current = str(Path.home() / 'Desktop')
            
            path = QFileDialog.getExistingDirectory(
                self, 
                '选择输出目录（将自动创建 公司名_时间戳.xlsx）', 
                current
            )
            if path:
                self.cashflow_path.setText(path)
                self.cashflow_path.setStyleSheet('background: white; color: #1e293b;')
                self.mode_hint.setText('💡 目录模式 → 将自动创建 公司名_时间戳.xlsx')
                self.append_log(f'📂 输出目录: {path}')
                self.auto_save()
        
        elif clicked == file_btn:
            current = self.cashflow_path.text().strip()
            current_dir = ''
            if current:
                p = Path(current)
                if p.suffix in ['.xlsx', '.xls']:
                    current_dir = str(p.parent)
                elif p.is_dir():
                    current_dir = str(p)
            
            path, _ = QFileDialog.getOpenFileName(
                self, 
                '选择已有现金流表文件', 
                current_dir,
                'Excel文件 (*.xlsx *.xls)'
            )
            if path:
                self.cashflow_path.setText(path)
                self.cashflow_path.setStyleSheet('background: white; color: #1e293b;')
                self.mode_hint.setText('💡 文件模式 → 将在已有文件中添加新Sheet')
                self.append_log(f'📄 现金流表: {Path(path).name}')
                self.auto_save()
    
    # ==================== 期间辅助方法 ====================
    def get_period_value(self):
        return self.period_input.text().strip()
    
    def get_quarter_code(self):
        text = self.period_input.text().strip()
        if text.upper().startswith('Q'):
            return text.upper()
        if text.endswith('月'):
            try:
                month = int(text.replace('月', ''))
                if month <= 3:
                    return 'Q1'
                elif month <= 6:
                    return 'Q2'
                elif month <= 9:
                    return 'Q3'
                else:
                    return 'Q4'
            except ValueError:
                pass
        return 'Q1'
    
    # ==================== 配置 ====================
    def load_config(self):
        """从 Config 单例加载配置到 GUI 控件"""
        classification = self.config_obj.data.classification
        yaml_config = self.config_manager.config
    
        # 加载期间
        saved_period = yaml_config.get('app', {}).get('period_value', '')
        if saved_period:
            self.period_input.setText(saved_period)
    
        # 加载银行名称
        banks = yaml_config.get('company', {}).get('banks', [])
        if banks:
            self.bank_name.setText(banks[0].get('name', ''))
    
        # 加载文件路径
        file_cfg = yaml_config.get('file', {})
    
        detail = file_cfg.get('detail_path', '')
        if detail:
            self.detail_path.setText(detail)
            self.detail_path.setStyleSheet('background: white; color: #1e293b;')
        else:
            self.detail_path.setStyleSheet('background: #f8fafc; color: #94a3b8;')
    
        cashflow = file_cfg.get('cashflow_file', '')
        if cashflow:
            self.cashflow_path.setText(cashflow)
            self.cashflow_path.setStyleSheet('background: white; color: #1e293b;')
            if Path(cashflow).suffix in ['.xlsx', '.xls']:
                self.mode_hint.setText('💡 文件模式 → 将在已有文件中添加新Sheet')
            else:
                self.mode_hint.setText('💡 目录模式 → 将自动创建 公司名_时间戳.xlsx')
    
        # ===== 加载支出规则到 GUI =====
        expense_rules = classification.expense_rules
        if expense_rules:
            lines = []
            for rule in expense_rules:
                keywords = []
                for cr in rule.contra_rules:
                    keywords.extend(cr.keywords)
                keywords.extend(rule.summary_keywords)
                if keywords:
                    lines.append(f"{rule.category}:{','.join(keywords)}")
            self.expense_rules.setText('\n'.join(lines))
        else:
            self.expense_rules.setText('')
    
        # ===== 加载排除关键词到 GUI =====
        exclude_keywords = classification.exclude_keywords
        if exclude_keywords:
            self.exclude_keywords.setText('\n'.join(exclude_keywords))
        else:
            self.exclude_keywords.setText('')
    
        # ===== 统一使用 _log_rules() 展示规则 =====
        self.append_log('📂 配置加载完成')
        self._log_rules() 
    
    def build_config(self):
        """从 GUI 控件构建配置字典"""
        period_value = self.get_period_value()
        
        rules = []
        for line in self.expense_rules.toPlainText().split('\n'):
            line = line.strip()
            if not line or ':' not in line:
                continue
            parts = line.split(':', 1)
            category = parts[0].strip()
            keywords = [k.strip() for k in parts[1].split(',') if k.strip()]
            if category and keywords:
                rules.append({
                    'category': category,
                    'contra_keywords': keywords,
                    'summary_keywords': [],
                    'enabled': True
                })
        
        exclude = [s.strip() for s in self.exclude_keywords.toPlainText().split('\n') if s.strip()]
        
        banks = []
        if self.bank_name.text().strip():
            banks.append({'name': self.bank_name.text().strip()})
        
        return {
            'app': {
                'period_value': period_value,
                'decimal_places': 2,
                'validation_threshold': 0.01
            },
            'company': {'banks': banks},
            'file': {
                'detail_path': self.detail_path.text().strip(),
                'cashflow_file': self.cashflow_path.text().strip()
            },
            'income_rules': self.config_manager.config.get('income_rules', []),
            'expense_rules': rules,
            'contra_filter': {'include_keywords': [], 'exclude_keywords': exclude},
            'column_mapping': {
                '产品收入': 15, '服务收入': 16, '其他收入': 17,
                '商品采购': 22, '运费': 23, '服务费': 24, '返点佣金': 25,
                '研发_人工成本': 26, '研发_材料设备': 27, '研发_服务费': 28, '研发_委外': 29,
                '销售_交通费': 30, '销售_住宿费': 31, '销售_车辆费': 32, '销售_市内交通': 33,
                '销售_招待费': 34, '销售_服务费': 35, '销售_经销返点': 36, '销售_其他': 37,
                '管理_办公费': 38, '管理_租金物业': 39, '管理_市内交通': 40,
                '管理_招待费': 41, '管理_差旅费': 42, '管理_人员薪资': 43,
                '管理_社保公积金': 44, '管理_员工福利': 45, '管理_其他': 46,
                '财务_手续费': 47, '财务_结息': 48, '财务_贷款利息': 49,
                '税金_增值税': 50, '税金_所得税': 51, '税金_印花税': 52, '税金_个税': 53,
                '固资_办公设备': 54, '固资_办公家具': 55,
                '营业外支出': 56, '罚款': 57, '违约金': 58
            },
            'data': {
                'skip_vouchers': ['期初余额', '本期合计', '本年累计', ''],
                'columns': {
                    'date': '日期', 'voucher': '凭证字号', 'description': '摘要',
                    'contra': '对方科目', 'debit': '借方', 'credit': '贷方',
                    'direction': '方向', 'balance': '余额'
                },
                'header_rows': 4, 'data_start_row': 5,
                'decimal_places': 2, 'validation_threshold': 0.01
            }
        }
    
    def auto_save(self):
        try:
            config = self.build_config()
            self.config_manager.save_config(config)
            # 重新加载 Config 单例
            self.config_obj.reload_classification()
            self.append_log('💾 配置已自动保存并重新加载')
        except Exception as e:
            logger.error(f"自动保存失败: {e}")
    
    # ==================== 日志 ====================
    def append_log(self, msg):
        self.log_text.append(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}')
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        logger.info(msg)
    
    def update_progress(self, value, label):
        self.progress_bar.setValue(value)
        self.progress_label.setText(label)
    

    def run_generator(self):
        if not self.bank_name.text().strip():
            QMessageBox.warning(self, '提示', '请输入银行名称')
            return
        if not self.cashflow_path.text().strip():
            QMessageBox.warning(self, '提示', '请选择输出目录或现金流表文件')
            return
        if not Path(self.detail_path.text().strip()).exists():
            QMessageBox.warning(self, '提示', '明细账文件不存在')
            return

        # ===== 验证规则 =====
        is_valid, errors = self._check_rules()
        if not is_valid:
            error_msg = "支出规则存在语法错误，请修正后重试：\n\n"
            for err in errors:
                error_msg += f"  • {err}\n"
            error_msg += "\n💡 提示：点击「验证规则」按钮可检查语法错误"
            QMessageBox.warning(self, '规则错误', error_msg)
            return

        # ===== 保存配置 =====
        config = self.build_config()
        self.config_manager.save_config(config)
        self.config_obj.reload_classification()
    
        # ===== 在日志中展示规则（统一格式） =====
        self.append_log('📋 规则已重新加载')
        self._log_rules()
    
        # ===== 继续执行 =====
    
        # ===== 继续执行 =====
        bank = self.bank_name.text().strip()
        cashflow_input = self.cashflow_path.text().strip()
        cashflow_path = Path(cashflow_input)
    
        if cashflow_path.suffix in ['.xlsx', '.xls']:
            cashflow_file = cashflow_path
            self.append_log(f'📄 使用已有现金流表: {cashflow_file.name}')
        else:
            dir_path = cashflow_path
            detail_name = Path(self.detail_path.text().strip()).stem
            clean_name = detail_name.replace('明细账', '').replace('明细', '').strip()
            if '_' in clean_name:
                parts = clean_name.split('_')
                company_name = parts[0].strip()
            else:
                company_name = clean_name
            if not company_name:
                company_name = '现金流表'
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{company_name}_{timestamp}.xlsx"
            cashflow_file = dir_path / filename
            self.append_log(f'📂 目录模式: {dir_path}')
            self.append_log(f'📄 将创建: {filename}')
    
        cashflow_file.parent.mkdir(parents=True, exist_ok=True)
    
        detail_path = Path(self.detail_path.text().strip())
        period_value = self.get_period_value()
        quarter = self.get_quarter_code()
        sheet_name = f"{bank}_{period_value}"
    
        self.append_log(f'📄 现金流表: {cashflow_file}')
        self.append_log(f'📅 Sheet: {sheet_name}')
    
        self.append_log(f'🚀 开始生成...')
        self.append_log(f'📁 明细账: {detail_path.name}')
    
        self.progress_bar.setValue(0)
        self.progress_label.setText('准备中...')
    
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
    
        self.worker_thread = WorkerThread(
            detail_path, bank, period_value, quarter,
            sheet_name, cashflow_file
        )
        self.worker_thread.progress_updated.connect(self.update_progress)
        self.worker_thread.log_updated.connect(self.append_log)
        self.worker_thread.finished.connect(self.on_finished)
        self.worker_thread.start() 
    
    def on_finished(self, success, result):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        if success:
            self.progress_label.setText('✅ 完成')
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #059669, stop:1 #10b981);
                    border-radius: 6px;
                }
            """)
            QMessageBox.information(self, '完成', f'报表已生成\n\n{result}')
        else:
            self.progress_label.setText('❌ 失败')
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #dc2626, stop:1 #ef4444);
                    border-radius: 6px;
                }
            """)
            if result != '已停止':
                QMessageBox.warning(self, '错误', f'生成失败\n\n{result}')
        
        self.worker_thread = None
    
    def stop_generator(self):
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.worker_thread.wait()
            self.worker_thread = None
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.append_log('⏹ 已停止')
            self.progress_label.setText('已停止')
            self.progress_bar.setValue(0)
    def _check_rules(self):
        """
        检查规则语法是否正确
        返回: (is_valid, errors_list)
        """
        text = self.expense_rules.toPlainText()
        errors = []
    
        # 获取所有行，保留原始行号
        lines = text.split('\n')
    
        for i, line in enumerate(lines, 1):
            original_line = line
            line = line.strip()
            if not line:
                continue
        
            # ===== 检查1: 是否包含冒号 =====
            if ':' not in line and '：' not in line:
                errors.append(f"第{i}行: 缺少冒号「:」 → \"{original_line}\"")
                continue
        
            # ===== 检查2: 是否使用了中文冒号 =====
            if '：' in line:
                errors.append(f"第{i}行: 使用了中文冒号「：」，请改为英文冒号「:」 → \"{original_line}\"")
                continue
        
            # ===== 检查3: 分割并验证 =====
            parts = line.split(':', 1)
            if len(parts) != 2:
                errors.append(f"第{i}行: 格式错误 → \"{original_line}\"")
                continue
        
            category = parts[0].strip()
            keywords = parts[1].strip()
        
            if not category:
                errors.append(f"第{i}行: 分类名称为空 → \"{original_line}\"")
        
            if not keywords:
                errors.append(f"第{i}行: 关键词为空 → \"{original_line}\"")
        
            # ===== 检查4: 关键词中是否有中文逗号 =====
            if '，' in keywords:
                errors.append(f"第{i}行: 关键词中使用了中文逗号「，」，请改为英文逗号「,」 → \"{original_line}\"")
        
            # ===== 检查5: 是否有连续逗号 =====
            if ',,' in keywords:
                errors.append(f"第{i}行: 存在连续逗号 → \"{original_line}\"")
        
            # ===== 检查6: 是否以逗号结尾 =====
            if keywords.endswith(','):
                errors.append(f"第{i}行: 关键词末尾有多余逗号 → \"{original_line}\"")
    
        return (len(errors) == 0, errors) 


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName('现金流量报表生成器')
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()