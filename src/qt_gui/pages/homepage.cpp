#include "homepage.h"
#include "utils/fontscale.h"
#include <QColor>
#include <QDateTime>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QMetaObject>
#include <QEasingCurve>
#include <QSizePolicy>

HomePage::HomePage(QWidget *parent) : QWidget(parent)
{
    setupUI();
}

void HomePage::setupUI()
{
    QVBoxLayout *mainLay = new QVBoxLayout(this);
    mainLay->setContentsMargins(24, 16, 24, 8);
    mainLay->setSpacing(12);

    // 顶部问候
    m_greeting = new QLabel(QStringLiteral("您好，欢迎使用康复指导系统"));
    m_greeting->setStyleSheet("font-size:20px; font-weight:bold; color:#1A5276; border:none;");
    mainLay->addWidget(m_greeting);

    // 中间区域：大号仪表盘 + 快捷入口
    QHBoxLayout *midLay = new QHBoxLayout();
    midLay->setSpacing(24);

    // 左侧仪表盘：放大显示，并在每次进入首页时从 0 加载到最后一次训练综合得分
    QVBoxLayout *gaugeLay = new QVBoxLayout();
    gaugeLay->setContentsMargins(0, 0, 0, 0);
    gaugeLay->setSpacing(10);
    m_gauge = new ArcGauge(this);
    m_gauge->setMinimumSize(320, 250);
    m_gauge->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    m_gauge->setValue(0);
    m_gauge->setLevel(m_lastScore.levelName);
    m_gauge->setLevelColor(QColor(m_lastScore.levelColor));
    gaugeLay->addWidget(m_gauge, 1, Qt::AlignCenter);

    m_levelLabel = new QLabel(m_lastScore.levelName);
    m_levelLabel->setStyleSheet("font-size:17px; color:#606060; border:none; font-weight:700;");
    m_levelLabel->setAlignment(Qt::AlignCenter);
    gaugeLay->addWidget(m_levelLabel, 0, Qt::AlignCenter);

    m_adviceLabel = new QLabel(QStringLiteral("康复建议：%1").arg(m_lastScore.advice));
    m_adviceLabel->setWordWrap(true);
    m_adviceLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    m_adviceLabel->setMinimumHeight(78);
    m_adviceLabel->setStyleSheet(
        "background:#FFFFFF; border:1px solid #D0DDE8; border-radius:14px;"
        "padding:10px 12px; font-size:14px; color:#4A4A4A; line-height:150%;");
    gaugeLay->addWidget(m_adviceLabel, 0);
    midLay->addLayout(gaugeLay, 2);

    // 右侧快捷入口
    QGridLayout *grid = new QGridLayout();
    grid->setSpacing(12);

    auto makeBtn = [](const QString &text, const QString &color) -> QPushButton* {
        QPushButton *b = new QPushButton(text);
        b->setMinimumSize(142, 70);
        b->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
        b->setStyleSheet(QString(
            "QPushButton { background:%1; color:white; border:none; border-radius:18px;"
            "font-size:17px; font-weight:bold; }"
            "QPushButton:pressed { background:%1; opacity:0.8; }"
        ).arg(color));
        return b;
    };

    m_btnAssess  = makeBtn(QStringLiteral("开始评估"), "#2E86C1");
    m_btnTrain   = makeBtn(QStringLiteral("开始训练"), "#27AE60");
    m_btnRecords = makeBtn(QStringLiteral("训练记录"), "#F39C12");
    m_btnMedicalAdvice = makeBtn(QStringLiteral("医疗建议"), "#16A085");
    m_btnSettings= makeBtn(QStringLiteral("系统设置"), "#8E44AD");

    grid->addWidget(m_btnAssess, 0, 0);
    grid->addWidget(m_btnTrain, 0, 1);
    grid->addWidget(m_btnRecords, 1, 0);
    grid->addWidget(m_btnMedicalAdvice, 1, 1);
    grid->addWidget(m_btnSettings, 2, 0, 1, 2);

    midLay->addLayout(grid, 1);
    midLay->setStretch(0, 2);
    midLay->setStretch(1, 1);
    mainLay->addLayout(midLay, 1);

    // 底部今日信息
    m_todayInfo = new QLabel(QStringLiteral("最近评估综合得分：%1分 | 级别：%2").arg(m_lastScore.compositeScore).arg(m_lastScore.levelName));
    m_todayInfo->setStyleSheet(
        "background:#FFFFFF; border:1px solid #D0DDE8; border-radius:12px;"
        "padding:12px; font-size:14px; color:#606060;");
    mainLay->addWidget(m_todayInfo);

    m_gaugeAnimation = new QPropertyAnimation(m_gauge, "value", this);
    m_gaugeAnimation->setDuration(1150);
    m_gaugeAnimation->setEasingCurve(QEasingCurve::OutCubic);

    // 快捷按钮连接
    auto switchToPage = [this](int pageIndex) {
        QWidget *w = parentWidget();
        while (w) {
            if (w->inherits("QMainWindow")) {
                QMetaObject::invokeMethod(w, "switchPage", Qt::DirectConnection, Q_ARG(int, pageIndex));
                break;
            }
            w = w->parentWidget();
        }
    };
    connect(m_btnAssess, &QPushButton::clicked, this, [switchToPage]() { switchToPage(1); });
    connect(m_btnTrain, &QPushButton::clicked, this, &HomePage::startTrainingRequested);
    connect(m_btnRecords, &QPushButton::clicked, this, [switchToPage]() { switchToPage(3); });
    connect(m_btnMedicalAdvice, &QPushButton::clicked, this, [switchToPage]() { switchToPage(4); });
    connect(m_btnSettings, &QPushButton::clicked, this, [switchToPage]() { switchToPage(5); });

    applyFontScale();
}

void HomePage::applyFontScale()
{
    const FontScale *fs = FontScale::instance();
    m_greeting->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:bold; color:#1A5276; border:none;")
            .arg(fs->px(20)));
    m_levelLabel->setStyleSheet(
        QStringLiteral("font-size:%1px; color:#606060; border:none; font-weight:700;")
            .arg(fs->px(17)));
    m_adviceLabel->setMinimumHeight(fs->largeMode() ? 96 : 78);
    m_adviceLabel->setStyleSheet(
        QStringLiteral(
            "background:#FFFFFF; border:1px solid #D0DDE8; border-radius:14px;"
            "padding:10px 12px; font-size:%1px; color:#4A4A4A; line-height:150%;")
            .arg(fs->px(14)));
    m_todayInfo->setStyleSheet(
        QStringLiteral(
            "background:#FFFFFF; border:1px solid #D0DDE8; border-radius:12px;"
            "padding:12px; font-size:%1px; color:#606060;")
            .arg(fs->px(14)));

    const int btnH = fs->largeMode() ? 84 : 70;
    const int btnFont = fs->px(17);
    auto restyleBtn = [btnH, btnFont](QPushButton *b, const QString &color) {
        if (!b) {
            return;
        }
        const bool large = FontScale::instance()->largeMode();
        b->setMinimumSize(large ? 156 : 142, btnH);
        b->setStyleSheet(QString(
            "QPushButton { background:%1; color:white; border:none; border-radius:18px;"
            "font-size:%2px; font-weight:bold; }"
            "QPushButton:pressed { background:%1; opacity:0.8; }"
        ).arg(color).arg(btnFont));
    };
    restyleBtn(m_btnAssess, QStringLiteral("#2E86C1"));
    restyleBtn(m_btnTrain, QStringLiteral("#27AE60"));
    restyleBtn(m_btnRecords, QStringLiteral("#F39C12"));
    restyleBtn(m_btnMedicalAdvice, QStringLiteral("#16A085"));
    restyleBtn(m_btnSettings, QStringLiteral("#8E44AD"));
}

void HomePage::refresh()
{
    QDateTime now = QDateTime::currentDateTime();
    int hour = now.time().hour();
    QString period = (hour < 12) ? QStringLiteral("早上好") : (hour < 18) ? QStringLiteral("下午好") : QStringLiteral("晚上好");
    m_greeting->setText(period + QStringLiteral("，欢迎使用康复指导系统"));

    if (m_lastScore.compositeScore > 0) {
        m_lastScore.advice = ScoreEngine::randomAdviceForScore(m_lastScore.compositeScore);
    }
    animateGaugeToLastScore();
}

void HomePage::setLastTrainingSummary(int compositeScore, const QString &levelName, const QString &levelColor, const QString &advice)
{
    m_lastScore.compositeScore = qBound(0, compositeScore, 100);
    m_lastScore.levelName = levelName.isEmpty() ? QStringLiteral("未评估") : levelName;
    m_lastScore.levelColor = levelColor.isEmpty() ? QStringLiteral("#A0A0A0") : levelColor;
    if (!advice.isEmpty()) {
        m_lastScore.advice = advice;
    } else if (m_lastScore.compositeScore > 0 && m_lastScore.advice.isEmpty()) {
        m_lastScore.advice = ScoreEngine::randomAdviceForScore(m_lastScore.compositeScore);
    } else if (m_lastScore.compositeScore <= 0) {
        m_lastScore.advice = QStringLiteral("请先完成一次测评，系统会根据综合得分给出康复建议。");
    }
}

void HomePage::animateGaugeToLastScore()
{
    const int target = qBound(0, m_lastScore.compositeScore, 100);
    const QString levelText = m_lastScore.levelName.isEmpty() ? QStringLiteral("未评估") : m_lastScore.levelName;
    const QString levelColor = m_lastScore.levelColor.isEmpty() ? QStringLiteral("#A0A0A0") : m_lastScore.levelColor;

    m_gauge->setLevel(levelText);
    m_gauge->setLevelColor(QColor(levelColor));
    m_levelLabel->setText(levelText);

    QString adviceText = m_lastScore.advice;
    if (target > 0 && adviceText.isEmpty()) {
        adviceText = ScoreEngine::randomAdviceForScore(target);
        m_lastScore.advice = adviceText;
    }
    if (target > 0) {
        m_todayInfo->setText(QStringLiteral("最近评估综合得分：%1分 | 级别：%2").arg(target).arg(levelText));
        m_adviceLabel->setText(QStringLiteral("康复建议：%1").arg(adviceText));
    } else {
        m_todayInfo->setText(QStringLiteral("暂无评估记录，请先在评估页完成测评。"));
        m_adviceLabel->setText(QStringLiteral("康复建议：请先完成一次测评，系统会根据综合得分随机给出建议。"));
    }

    if (m_gaugeAnimation) {
        m_gaugeAnimation->stop();
        m_gauge->setValue(0);
        m_gaugeAnimation->setStartValue(0);
        m_gaugeAnimation->setEndValue(target);
        m_gaugeAnimation->start();
    } else {
        m_gauge->setValue(target);
    }
}

void HomePage::onScoreUpdated(const ScoreResult &result)
{
    m_lastScore = result;
    if (m_lastScore.levelName.isEmpty()) {
        m_lastScore.levelName = QStringLiteral("未评估");
    }
    if (m_lastScore.levelColor.isEmpty()) {
        m_lastScore.levelColor = QStringLiteral("#A0A0A0");
    }
    if (m_lastScore.advice.isEmpty() && m_lastScore.compositeScore > 0) {
        m_lastScore.advice = ScoreEngine::randomAdviceForScore(m_lastScore.compositeScore);
    }
    animateGaugeToLastScore();
}
