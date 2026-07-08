#include "widget.h"
#include "ui_widget.h"
#include "mainwindow.h"

#include <QtGlobal>
#include <QEvent>
#include <QFile>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QLayout>
#include <QGuiApplication>
#include <QLabel>
#include <QPixmap>
#include <QScreen>
#include <QRect>
#include <QSizePolicy>
#include <QPushButton>
#include <QResizeEvent>
#include <QTextStream>
#include <QVBoxLayout>

Widget::Widget(QWidget *parent)
    : QWidget(parent)
    , ui(new Ui::Widget)
    , m_pictureLabel(nullptr)
    , m_logoLabel(nullptr)
    , m_currentPicturePath(":/res/pic/3.png")
    , m_currentStyleIndex(3)
    , m_mainWindow(nullptr)
{
    ui->setupUi(this);
    setWindowTitle(QStringLiteral("居家康复动作指导教练"));

    setupResponsiveLayout();
    fitWindowToCurrentScreen();

    setupPictureLabel();
    setupLogoLabel();

    connect(ui->btn_1, SIGNAL(clicked(bool)), this, SLOT(set_style()));
    connect(ui->btn_2, SIGNAL(clicked(bool)), this, SLOT(set_style()));
    connect(ui->btn_3, SIGNAL(clicked(bool)), this, SLOT(set_style()));
    connect(ui->btn_4, SIGNAL(clicked(bool)), this, SLOT(set_style()));

    connect(ui->btn_login, &QPushButton::clicked, this, &Widget::onLoginClicked);

    setupQuickStartPanel();
    applyLoginStyle(m_currentStyleIndex);
}


void Widget::setupResponsiveLayout()
{
    setMinimumSize(800, 450);

    // 让 Qt Designer 中原本固定在左上角的登录内容进入背景容器布局，
    // 在大屏居中，在小屏自动压缩，避免不同分辨率下出现裁切或偏移。
    QGridLayout *backgroundLayout = qobject_cast<QGridLayout *>(ui->frame_background->layout());
    if (!backgroundLayout) {
        backgroundLayout = new QGridLayout(ui->frame_background);
    }
    backgroundLayout->setContentsMargins(16, 16, 16, 16);
    backgroundLayout->setSpacing(0);
    backgroundLayout->addWidget(ui->layoutWidget, 0, 0, Qt::AlignCenter);

    ui->layoutWidget->setMinimumSize(720, 460);
    ui->layoutWidget->setMaximumSize(1180, 760);
    ui->layoutWidget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    ui->frame->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    ui->frame->setMinimumSize(0, 0);
    if (ui->frame->layout()) {
        ui->frame->layout()->setContentsMargins(0, 0, 0, 0);
    }

    // 入口内容面板和右侧图片面板保持 1:1 等比扩展。
    // 将最小宽度控制在小屏也能容纳的范围内，避免入口面板被左右挤压后遮挡。
    ui->frame_login->setMinimumSize(320, 420);
    ui->frame_login->setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX);
    ui->frame_login->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    ui->frame_pic->setMinimumSize(320, 420);
    ui->frame_pic->setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX);
    ui->frame_pic->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    if (ui->horizontalLayout_8) {
        ui->horizontalLayout_8->setSpacing(0);
        ui->horizontalLayout_8->setStretch(0, 1);
        ui->horizontalLayout_8->setStretch(1, 1);
    }

    // 入口面板内部也使用布局承载，消除绝对坐标带来的拉伸后错位。
    QGridLayout *loginLayout = qobject_cast<QGridLayout *>(ui->frame_login->layout());
    if (!loginLayout) {
        loginLayout = new QGridLayout(ui->frame_login);
    }
    loginLayout->setContentsMargins(22, 24, 22, 24);
    loginLayout->setSpacing(0);
    loginLayout->addWidget(ui->layoutWidgetLoginFields, 0, 0);
    ui->layoutWidgetLoginFields->setMinimumSize(0, 0);
    ui->layoutWidgetLoginFields->setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX);
    ui->layoutWidgetLoginFields->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    ui->label_title->setAlignment(Qt::AlignCenter);
    ui->label_title->setText(QStringLiteral("欢迎使用康复指导系统"));

    ui->label_login->setAlignment(Qt::AlignCenter);

    // 账户/密码输入框：去掉会造成小窗口裁切的固定左右宽度，使用弹性伸缩，
    // 同时保留足够高度，保证图标、边框、占位文字和输入文字都无遮挡。
    ui->frame_user_name->setMinimumSize(0, 54);
    ui->frame_pwd->setMinimumSize(0, 54);
    ui->frame_user_name->setMaximumHeight(54);
    ui->frame_pwd->setMaximumHeight(54);
    ui->frame_user_name->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    ui->frame_pwd->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    if (ui->horizontalSpacer_20) ui->horizontalSpacer_20->changeSize(20, 20, QSizePolicy::Fixed, QSizePolicy::Minimum);
    if (ui->horizontalSpacer_22) ui->horizontalSpacer_22->changeSize(20, 20, QSizePolicy::Fixed, QSizePolicy::Minimum);
    if (ui->horizontalSpacer_6)  ui->horizontalSpacer_6->changeSize(20, 20, QSizePolicy::Fixed, QSizePolicy::Minimum);
    if (ui->horizontalSpacer_19) ui->horizontalSpacer_19->changeSize(20, 20, QSizePolicy::Fixed, QSizePolicy::Minimum);
    if (ui->horizontalSpacer_21) ui->horizontalSpacer_21->changeSize(0, 20, QSizePolicy::Fixed, QSizePolicy::Minimum);
    if (ui->horizontalSpacer_5)  ui->horizontalSpacer_5->changeSize(0, 20, QSizePolicy::Fixed, QSizePolicy::Minimum);

    if (ui->horizontalLayout_10) {
        ui->horizontalLayout_10->setContentsMargins(0, 0, 0, 0);
        ui->horizontalLayout_10->setSpacing(0);
        ui->horizontalLayout_10->setStretch(0, 0);
        ui->horizontalLayout_10->setStretch(1, 1);
        ui->horizontalLayout_10->setStretch(2, 0);
    }
    if (ui->horizontalLayout_2) {
        ui->horizontalLayout_2->setContentsMargins(0, 0, 0, 0);
        ui->horizontalLayout_2->setSpacing(0);
        ui->horizontalLayout_2->setStretch(0, 0);
        ui->horizontalLayout_2->setStretch(1, 1);
        ui->horizontalLayout_2->setStretch(2, 0);
    }
    if (ui->horizontalLayout_11) {
        ui->horizontalLayout_11->setContentsMargins(0, 0, 0, 0);
        ui->horizontalLayout_11->setSpacing(10);
    }
    if (ui->horizontalLayout_3) {
        ui->horizontalLayout_3->setContentsMargins(0, 0, 0, 0);
        ui->horizontalLayout_3->setSpacing(10);
    }
    if (ui->gridLayout_4) ui->gridLayout_4->setContentsMargins(12, 7, 12, 7);
    if (ui->gridLayout)   ui->gridLayout->setContentsMargins(12, 7, 12, 7);

    ui->label_user_name->setFixedSize(28, 28);
    ui->label_pwd->setFixedSize(28, 28);

    ui->lineE_user_name->setMinimumSize(0, 38);
    ui->lineE_pwd->setMinimumSize(0, 38);
    ui->lineE_user_name->setMaximumHeight(38);
    ui->lineE_pwd->setMaximumHeight(38);
    ui->lineE_user_name->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    ui->lineE_pwd->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    ui->btn_login->setMinimumSize(220, 46);
    ui->btn_register->setMinimumSize(220, 46);
    ui->btn_login->setMaximumWidth(QWIDGETSIZE_MAX);
    ui->btn_register->setMaximumWidth(QWIDGETSIZE_MAX);
    ui->btn_login->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    ui->btn_register->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

void Widget::setupQuickStartPanel()
{
    // 删除原登录/注册交互：隐藏账号、密码、注册等旧控件，仅保留主题选择和一键进入按钮。
    ui->layoutWidgetLoginFields->hide();
    ui->frame_user_name->hide();
    ui->frame_pwd->hide();
    ui->btn_register->hide();
    ui->label_login->hide();

    ui->btn_login->setText(QStringLiteral("开始使用"));
    ui->btn_login->setMinimumSize(260, 58);
    ui->btn_login->setMaximumHeight(58);
    ui->btn_login->setCursor(Qt::PointingHandCursor);

    QGridLayout *loginLayout = qobject_cast<QGridLayout *>(ui->frame_login->layout());
    if (!loginLayout) {
        loginLayout = new QGridLayout(ui->frame_login);
        loginLayout->setContentsMargins(22, 24, 22, 24);
    }

    QWidget *quickPanel = new QWidget(ui->frame_login);
    quickPanel->setObjectName(QStringLiteral("quickStartPanel"));
    quickPanel->setAttribute(Qt::WA_StyledBackground, true);
    quickPanel->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    QVBoxLayout *quickLayout = new QVBoxLayout(quickPanel);
    quickLayout->setContentsMargins(24, 28, 24, 28);
    quickLayout->setSpacing(18);

    // 按用户要求：删除一级登录页中的说明文字，只保留进入按钮。
    ui->btn_login->setParent(quickPanel);
    ui->btn_login->setVisible(true);

    quickLayout->addStretch(1);
    quickLayout->addWidget(ui->btn_login, 0, Qt::AlignCenter);
    quickLayout->addStretch(1);

    loginLayout->addWidget(quickPanel, 0, 0);
}

void Widget::fitWindowToCurrentScreen()
{
    QScreen *screen = QGuiApplication::primaryScreen();
    if (!screen) {
        resize(1280, 720);
        return;
    }

    const QRect available = screen->availableGeometry();
    const int targetW = qMin(1280, qMax(800, int(available.width() * 0.90)));
    const int targetH = qMin(720, qMax(450, int(available.height() * 0.88)));
    resize(qMin(targetW, available.width()), qMin(targetH, available.height()));
    move(available.center() - rect().center());
}


bool Widget::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == ui->frame_pic && event->type() == QEvent::Resize) {
        updatePicture();
        updateLogo();
    }

    return QWidget::eventFilter(watched, event);
}

void Widget::onLoginClicked()
{
    // “开始使用”直接进入二级页面，不再进行账号、密码、注册或本地账户校验。
    if (m_mainWindow) {
        m_mainWindow->close();
        m_mainWindow = nullptr;
    }

    m_mainWindow = new MainWindow(m_currentStyleIndex);
    m_mainWindow->setAttribute(Qt::WA_DeleteOnClose);
    connect(m_mainWindow, &QObject::destroyed, this, [this](QObject *) {
        m_mainWindow = nullptr;
    });

    m_mainWindow->show();
    hide();
}

void Widget::setupPictureLabel()
{
    ui->frame_pic->setStyleSheet(QStringLiteral("border: none; background: transparent;"));

    ui->frame_pic->installEventFilter(this);

    m_pictureLabel = new QLabel(ui->frame_pic);
    m_pictureLabel->setAlignment(Qt::AlignCenter);
    m_pictureLabel->setScaledContents(false);
    m_pictureLabel->setAttribute(Qt::WA_TransparentForMouseEvents);
    m_pictureLabel->setGeometry(ui->frame_pic->rect());
}

void Widget::setupLogoLabel()
{
    m_logoLabel = new QLabel(ui->frame_pic);
    m_logoLabel->setObjectName(QStringLiteral("loginLogoLabel"));
    m_logoLabel->setAlignment(Qt::AlignCenter);
    m_logoLabel->setScaledContents(false);
    m_logoLabel->setAttribute(Qt::WA_TransparentForMouseEvents);
    m_logoLabel->setStyleSheet(QStringLiteral("border: none; background: transparent;"));
    m_logoLabel->raise();

    updateLogo();
}

void Widget::setPicture(const QString &picturePath)
{
    m_currentPicturePath = picturePath;
    updatePicture();
}

void Widget::updatePicture()
{
    if (!m_pictureLabel) {
        return;
    }

    m_pictureLabel->setGeometry(ui->frame_pic->rect());

    QPixmap pixmap(m_currentPicturePath);
    if (pixmap.isNull()) {
        m_pictureLabel->clear();
        return;
    }

    const QSize targetSize = ui->frame_pic->size();
    // 右侧图片跟随 frame_pic 等比填充。frame_pic 已与左侧入口面板保持相同伸缩比例，
    // 这里使用 KeepAspectRatioByExpanding 避免图片周围出现过多空白。
    m_pictureLabel->setPixmap(pixmap.scaled(targetSize, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation));
    updateLogo();
}

void Widget::updateLogo()
{
    if (!m_logoLabel) {
        return;
    }

    QPixmap logo(QStringLiteral(":/res/pic/logo.png"));
    if (logo.isNull()) {
        m_logoLabel->clear();
        return;
    }

    const QSize area = ui->frame_pic->size();
    if (area.isEmpty()) {
        return;
    }

    const int maxWidth = qBound(180, int(area.width() * 0.58), 420);
    const int maxHeight = qBound(42, int(area.height() * 0.14), 86);
    const QPixmap scaledLogo = logo.scaled(QSize(maxWidth, maxHeight),
                                           Qt::KeepAspectRatio,
                                           Qt::SmoothTransformation);

    const int marginX = qBound(14, area.width() / 22, 34);
    const int marginY = qBound(14, area.height() / 26, 30);
    m_logoLabel->setPixmap(scaledLogo);
    m_logoLabel->setFixedSize(scaledLogo.size());
    m_logoLabel->move(area.width() - scaledLogo.width() - marginX, marginY);
    m_logoLabel->raise();
}


void Widget::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updatePicture();
    updateLogo();
}

QString Widget::loginStylePath(int styleIndex) const
{
    return QString(":/res/qss/style-%1.qss").arg(qBound(1, styleIndex, 4));
}

QString Widget::loginPicturePath(int styleIndex) const
{
    return QString(":/res/pic/%1.png").arg(qBound(1, styleIndex, 4));
}

void Widget::applyLoginStyle(int styleIndex)
{
    m_currentStyleIndex = qBound(1, styleIndex, 4);

    QFile file(loginStylePath(m_currentStyleIndex));
    if (file.open(QFile::ReadOnly)) {
        QTextStream filetext(&file);
        const QString stylesheet = filetext.readAll();
        setStyleSheet(stylesheet);
        file.close();
    }

    ui->frame_pic->setStyleSheet(QStringLiteral("border: none; background: transparent;"));
    setPicture(loginPicturePath(m_currentStyleIndex));
}

void Widget::set_style()
{
    QPushButton *btn = qobject_cast<QPushButton *>(sender());
    if (!btn) {
        return;
    }

    int styleIndex = m_currentStyleIndex;
    if ("btn_1" == btn->objectName()) {        // 粉色
        styleIndex = 1;
    } else if ("btn_2" == btn->objectName()) { // 黄蓝
        styleIndex = 2;
    } else if ("btn_3" == btn->objectName()) { // 浅紫
        styleIndex = 3;
    } else if ("btn_4" == btn->objectName()) { // 青绿
        styleIndex = 4;
    }

    applyLoginStyle(styleIndex);
}

Widget::~Widget()
{
    delete ui;
}
