#include "recordspage.h"

#include "models/datastorage.h"
#include "utils/fontscale.h"

#include <algorithm>
#include <functional>
#include <QFrame>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QHBoxLayout>
#include <QtGlobal>
#include <QMessageBox>
#include <QSizePolicy>
#include <QVBoxLayout>
#include <QVector>
#include <QVariant>

namespace {

int detectTrainingLevel(int fallbackLevel, const QString &text)
{
    if (text.contains(QStringLiteral("L1")) || text.contains(QStringLiteral("卧床"))) return 1;
    if (text.contains(QStringLiteral("L2")) || text.contains(QStringLiteral("坐姿"))) return 2;
    if (text.contains(QStringLiteral("L3")) || text.contains(QStringLiteral("站立主动"))) return 3;
    if (text.contains(QStringLiteral("L4")) || text.contains(QStringLiteral("全幅主动")) || text.contains(QStringLiteral("太极"))) return 4;
    return qBound(1, fallbackLevel, 4);
}

QStringList blockNamesForLevel(int level, const QString &text)
{
    const int l = detectTrainingLevel(level, text);
    QStringList names;
    switch (l) {
    case 1:
        names << QStringLiteral("仰卧肩关节被动外旋") << QStringLiteral("仰卧肘关节屈伸")
              << QStringLiteral("仰卧踝泵运动") << QStringLiteral("仰卧深呼吸训练");
        break;
    case 2:
        names << QStringLiteral("坐姿肩关节前屈上举") << QStringLiteral("坐姿肩关节外展")
              << QStringLiteral("坐姿膝关节伸展") << QStringLiteral("坐姿上肢协调性训练");
        break;
    case 3:
        names << QStringLiteral("站立肩关节全幅前屈") << QStringLiteral("站立半蹲训练")
              << QStringLiteral("站立重心转移") << QStringLiteral("站立单脚平衡");
        break;
    default:
        names << QStringLiteral("太极拳式复合运动") << QStringLiteral("站立上肢负重训练")
              << QStringLiteral("站立单脚平衡进阶") << QStringLiteral("站立身体旋转协调");
        break;
    }
    return names;
}

QList<int> blockScoresFromDims(const ScoreResult &result, int /*composite*/, int count)
{
    QList<int> scores;
    for (int i = 0; i < count; ++i) {
        const QString key = QStringLiteral("block_%1").arg(i + 1);
        if (!result.dims.contains(key)) {
            return QList<int>();
        }
        scores.append(qBound(0, qRound(result.dims.value(key) * 100.0), 100));
    }
    return scores;
}

} // namespace

RecordsPage::RecordsPage(QWidget *parent) : QWidget(parent)
{
    setupUI();
}

void RecordsPage::setupUI()
{
    QVBoxLayout *root = new QVBoxLayout(this);
    root->setContentsMargins(24, 16, 24, 12);
    root->setSpacing(0);

    m_stack = new QStackedWidget(this);
    m_stack->setStyleSheet("QStackedWidget{background:transparent; border:none;}");
    root->addWidget(m_stack, 1);

    buildListPage();
    buildDetailPage();
    loadStoredData();
    rebuildSummaryRecord();
    m_stack->setCurrentWidget(m_listPage);
}

void RecordsPage::buildListPage()
{
    m_listPage = new QWidget(this);
    m_listPage->setStyleSheet("background:transparent; border:none;");

    QVBoxLayout *lay = new QVBoxLayout(m_listPage);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->setSpacing(12);

    m_title = new QLabel(QStringLiteral("训练记录"), m_listPage);
    m_title->setStyleSheet("font-size:24px; font-weight:900; color:#1A5276; border:none;");
    lay->addWidget(m_title);

    m_summary = new QLabel(m_listPage);
    m_summary->setStyleSheet("font-size:14px; color:#606060; border:none;");
    lay->addWidget(m_summary);

    m_scrollArea = new QScrollArea(m_listPage);
    m_scrollArea->setWidgetResizable(true);
    m_scrollArea->setStyleSheet("QScrollArea{border:none; background:transparent;}");

    m_scoreContainer = new QWidget(m_scrollArea);
    m_scoreContainer->setStyleSheet("background:transparent; border:none;");
    m_scoreLayout = new QVBoxLayout(m_scoreContainer);
    m_scoreLayout->setContentsMargins(0, 0, 0, 0);
    m_scoreLayout->setSpacing(12);

    m_scrollArea->setWidget(m_scoreContainer);
    lay->addWidget(m_scrollArea, 1);

    m_stack->addWidget(m_listPage);
}

void RecordsPage::buildDetailPage()
{
    m_detailPage = new QWidget(this);
    m_detailPage->setStyleSheet("background:transparent; border:none;");

    QVBoxLayout *lay = new QVBoxLayout(m_detailPage);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->setSpacing(12);

    QHBoxLayout *topLay = new QHBoxLayout();
    topLay->setSpacing(12);
    m_backBtn = new QPushButton(QStringLiteral("← 返回训练记录"), m_detailPage);
    m_backBtn->setMinimumHeight(38);
    m_backBtn->setCursor(Qt::PointingHandCursor);
    m_backBtn->setStyleSheet(
        "QPushButton{background:#FFFFFF; color:#1A5276; border:1px solid #C8D8E8; border-radius:10px;"
        "font-size:14px; font-weight:bold; padding:4px 16px;}"
        "QPushButton:hover{background:#E8F4FD;}"
        "QPushButton:pressed{background:#D6EAF8;}"
    );
    connect(m_backBtn, &QPushButton::clicked, this, [this]() {
        m_stack->setCurrentWidget(m_listPage);
    });
    topLay->addWidget(m_backBtn, 0, Qt::AlignLeft);
    topLay->addStretch(1);
    lay->addLayout(topLay);

    QFrame *hero = new QFrame(m_detailPage);
    hero->setObjectName("detailHero");
    hero->setStyleSheet(
        "QFrame#detailHero{background:#FFFFFF; border:1px solid #D0DDE8; border-radius:18px;}"
        "QLabel{border:none; background:transparent;}"
    );
    QVBoxLayout *heroLay = new QVBoxLayout(hero);
    heroLay->setContentsMargins(22, 18, 22, 18);
    heroLay->setSpacing(10);

    m_detailTitle = new QLabel(hero);
    m_detailTitle->setStyleSheet("font-size:24px; font-weight:900; color:#1A5276;");
    heroLay->addWidget(m_detailTitle);

    m_detailMeta = new QLabel(hero);
    m_detailMeta->setWordWrap(true);
    m_detailMeta->setStyleSheet("font-size:15px; color:#4A4A4A;");
    heroLay->addWidget(m_detailMeta);

    QHBoxLayout *scoreLay = new QHBoxLayout();
    scoreLay->setSpacing(16);
    m_detailComposite = new QLabel(hero);
    m_detailComposite->setAlignment(Qt::AlignCenter);
    m_detailComposite->setMinimumHeight(86);
    m_detailComposite->setStyleSheet(
        "background:#E8F4FD; color:#1A5276; border:1px solid #BFD7EA; border-radius:16px;"
        "font-size:28px; font-weight:900; padding:8px;"
    );
    m_detailLevel = new QLabel(hero);
    m_detailLevel->setAlignment(Qt::AlignCenter);
    m_detailLevel->setMinimumHeight(86);
    m_detailLevel->setStyleSheet(
        "background:#F8FBFF; color:#2E86C1; border:1px solid #D0DDE8; border-radius:16px;"
        "font-size:18px; font-weight:800; padding:8px;"
    );
    scoreLay->addWidget(m_detailComposite, 2);
    scoreLay->addWidget(m_detailLevel, 1);
    heroLay->addLayout(scoreLay);

    lay->addWidget(hero, 0);

    m_detailScroll = new QScrollArea(m_detailPage);
    m_detailScroll->setWidgetResizable(true);
    m_detailScroll->setFrameShape(QFrame::NoFrame);
    m_detailScroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_detailScroll->setStyleSheet("QScrollArea{background:transparent; border:none;}");

    QWidget *detailBody = new QWidget(m_detailScroll);
    detailBody->setStyleSheet("background:transparent; border:none;");
    QVBoxLayout *bodyLay = new QVBoxLayout(detailBody);
    bodyLay->setContentsMargins(0, 0, 0, 0);
    bodyLay->setSpacing(12);

    m_detailScoresPanel = new QWidget(detailBody);
    m_detailScoresPanel->setStyleSheet(
        "QWidget{background:#FFFFFF; border:1px solid #D0DDE8; border-radius:18px;}"
        "QLabel{border:none; background:transparent;}"
        "QProgressBar{border:1px solid #D0DDE8; border-radius:8px; background:#EDF3F8; height:16px; text-align:center;}"
        "QProgressBar::chunk{background:#2E86C1; border-radius:8px;}"
    );
    QVBoxLayout *panelLay = new QVBoxLayout(m_detailScoresPanel);
    panelLay->setContentsMargins(22, 18, 22, 18);
    panelLay->setSpacing(12);

    QLabel *scoreTitle = new QLabel(QStringLiteral("四个功能块详细评分"), m_detailScoresPanel);
    m_detailScoreTitle = scoreTitle;
    scoreTitle->setStyleSheet("font-size:20px; font-weight:900; color:#1A5276;");
    panelLay->addWidget(scoreTitle);

    m_detailScoresGrid = new QGridLayout();
    m_detailScoresGrid->setHorizontalSpacing(14);
    m_detailScoresGrid->setVerticalSpacing(12);
    panelLay->addLayout(m_detailScoresGrid);

    m_detailAdvice = new QLabel(m_detailScoresPanel);
    m_detailAdvice->setWordWrap(true);
    m_detailAdvice->setStyleSheet(
        "background:#FFF9E8; color:#6C4F00; border:1px solid #F5D76E; border-radius:12px;"
        "font-size:14px; padding:10px;"
    );
    panelLay->addWidget(m_detailAdvice);

    bodyLay->addWidget(m_detailScoresPanel, 0);
    bodyLay->addStretch(1);
    m_detailScroll->setWidget(detailBody);
    lay->addWidget(m_detailScroll, 1);

    m_stack->addWidget(m_detailPage);
}

void RecordsPage::refresh()
{
    loadStoredData();
    rebuildSummaryRecord();
    m_stack->setCurrentWidget(m_listPage);
    m_openDetailIndex = -1;
}

void RecordsPage::applyFontScale()
{
    const FontScale *fs = FontScale::instance();
    if (m_title) {
        m_title->setStyleSheet(
            QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276; border:none;")
                .arg(fs->px(24)));
    }
    if (m_summary) {
        m_summary->setStyleSheet(
            QStringLiteral("font-size:%1px; color:#606060; border:none;")
                .arg(fs->px(14)));
    }
    if (m_backBtn) {
        m_backBtn->setMinimumHeight(fs->largeMode() ? 46 : 38);
        m_backBtn->setStyleSheet(
            QStringLiteral(
                "QPushButton{background:#FFFFFF; color:#1A5276; border:1px solid #C8D8E8; border-radius:10px;"
                "font-size:%1px; font-weight:bold; padding:4px 16px;}"
                "QPushButton:hover{background:#E8F4FD;}"
                "QPushButton:pressed{background:#D6EAF8;}")
                .arg(fs->px(14)));
    }
    if (m_detailTitle) {
        m_detailTitle->setStyleSheet(
            QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276;")
                .arg(fs->px(24)));
    }
    if (m_detailMeta) {
        m_detailMeta->setStyleSheet(
            QStringLiteral("font-size:%1px; color:#4A4A4A;").arg(fs->px(15)));
    }
    if (m_detailComposite) {
        m_detailComposite->setMinimumHeight(fs->largeMode() ? 98 : 86);
        m_detailComposite->setStyleSheet(
            QStringLiteral(
                "background:#E8F4FD; color:#1A5276; border:1px solid #BFD7EA; border-radius:16px;"
                "font-size:%1px; font-weight:900; padding:8px;")
                .arg(fs->px(28)));
    }
    if (m_detailLevel) {
        m_detailLevel->setMinimumHeight(fs->largeMode() ? 98 : 86);
        m_detailLevel->setStyleSheet(
            QStringLiteral(
                "background:#F8FBFF; color:#2E86C1; border:1px solid #D0DDE8; border-radius:16px;"
                "font-size:%1px; font-weight:800; padding:8px;")
                .arg(fs->px(18)));
    }
    if (m_detailScoreTitle) {
        m_detailScoreTitle->setStyleSheet(
            QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276;")
                .arg(fs->px(20)));
    }
    if (m_detailAdvice) {
        m_detailAdvice->setStyleSheet(
            QStringLiteral(
                "background:#FFF9E8; color:#6C4F00; border:1px solid #F5D76E; border-radius:12px;"
                "font-size:%1px; padding:10px;")
                .arg(fs->px(14)));
    }

    const int openDetail = m_openDetailIndex;
    rebuildSummaryRecord();
    if (openDetail >= 0 && openDetail < m_records.size()
        && m_stack && m_stack->currentWidget() == m_detailPage) {
        showRecordDetail(openDetail);
    }
}

void RecordsPage::appendTrainingRecord(const QString &actionName, const ScoreResult &result, int completion)
{
    loadStoredData();

    const int composite = qBound(0, result.compositeScore, 100);
    if (composite <= 0 && result.dims.isEmpty()) {
        return;
    }

    const int nextIndex = m_records.isEmpty() ? 1 : (m_records.last().index + 1);
    const QString advice = result.advice.isEmpty()
            ? ScoreEngine::randomAdviceForScore(composite)
            : result.advice;

    TrainRecord record;
    record.index = nextIndex;
    record.source = QStringLiteral("training_integrated");
    record.actionName = actionName.trimmed().isEmpty() ? QStringLiteral("康复训练") : actionName.trimmed();
    record.compositeScore = composite;
    record.completion = qBound(0, completion < 0 ? composite : completion, 100);
    record.level = result.levelName.isEmpty()
            ? ScoreEngine::levelName(ScoreEngine::scoreToLevel(composite))
            : result.levelName;
    record.timestamp = result.timestamp.isValid() ? result.timestamp : QDateTime::currentDateTime();
    record.blockNames = result.blockNames;
    record.blockScores = result.blockScores;
    if (record.blockNames.size() != 4 || record.blockScores.size() != 4) {
        record.blockNames = blockNamesForLevel(result.level, record.actionName);
        record.blockScores = blockScoresFromDims(result, composite, record.blockNames.size());
    }
    if (record.blockNames.size() != 4 || record.blockScores.size() != 4) {
        return;
    }
    record.advice = advice;

    m_records.append(record);
    saveStoredData();
    rebuildSummaryRecord();
}

void RecordsPage::loadStoredData()
{
    if (m_recordsLoaded) {
        return;
    }
    m_recordsLoaded = true;
    m_records.clear();

    QJsonObject root;
    if (!DataStorage::readJsonFile(QStringLiteral("training_records.json"), &root)) {
        return;
    }

    const QJsonArray arr = root.value(QStringLiteral("records")).toArray();
    for (const QJsonValue &value : arr) {
        const QJsonObject obj = value.toObject();
        if (obj.isEmpty()) {
            continue;
        }

        const QString source = obj.value(QStringLiteral("source")).toString();
        if (!source.isEmpty() && source != QStringLiteral("training_integrated") && source != QStringLiteral("training")) {
            continue;
        }

        TrainRecord record;
        record.source = source.isEmpty() ? QStringLiteral("training_integrated") : source;
        record.index = obj.value(QStringLiteral("index")).toInt(m_records.size() + 1);
        record.actionName = obj.value(QStringLiteral("actionName")).toString(QStringLiteral("康复综合训练"));
        record.compositeScore = qBound(0, obj.value(QStringLiteral("compositeScore")).toInt(0), 100);
        record.completion = qBound(0, obj.value(QStringLiteral("completion")).toInt(record.compositeScore), 100);
        record.level = obj.value(QStringLiteral("level")).toString(ScoreEngine::levelName(ScoreEngine::scoreToLevel(record.compositeScore)));
        record.timestamp = QDateTime::fromString(obj.value(QStringLiteral("timestamp")).toString(), Qt::ISODateWithMs);

        const QJsonArray nameArr = obj.value(QStringLiteral("blockNames")).toArray();
        for (const QJsonValue &nameValue : nameArr) {
            const QString name = nameValue.toString().trimmed();
            if (!name.isEmpty()) {
                record.blockNames.append(name);
            }
        }

        const QJsonArray scoreArr = obj.value(QStringLiteral("blockScores")).toArray();
        for (const QJsonValue &scoreValue : scoreArr) {
            record.blockScores.append(qBound(0, scoreValue.toInt(0), 100));
        }

        // 不再兼容旧版单动作/六维度训练记录：必须包含四个功能块名称和四个功能块得分。
        if (record.blockNames.size() != 4 || record.blockScores.size() != 4 || record.compositeScore <= 0) {
            continue;
        }

        record.advice = obj.value(QStringLiteral("advice")).toString(ScoreEngine::randomAdviceForScore(record.compositeScore));
        m_records.append(record);
    }
}

void RecordsPage::saveStoredData() const
{
    QJsonArray arr;
    for (const TrainRecord &record : m_records) {
        QJsonObject obj;
        obj.insert(QStringLiteral("index"), record.index);
        obj.insert(QStringLiteral("source"), QStringLiteral("training_integrated"));
        obj.insert(QStringLiteral("actionName"), record.actionName);
        obj.insert(QStringLiteral("compositeScore"), record.compositeScore);
        obj.insert(QStringLiteral("completion"), record.completion);
        obj.insert(QStringLiteral("level"), record.level);
        obj.insert(QStringLiteral("timestamp"), record.timestamp.isValid()
                   ? record.timestamp.toString(Qt::ISODateWithMs)
                   : QString());
        QJsonArray blockNameArr;
        for (const QString &name : record.blockNames) {
            blockNameArr.append(name);
        }
        QJsonArray blockScoreArr;
        for (int score : record.blockScores) {
            blockScoreArr.append(qBound(0, score, 100));
        }
        obj.insert(QStringLiteral("blockNames"), blockNameArr);
        obj.insert(QStringLiteral("blockScores"), blockScoreArr);
        obj.insert(QStringLiteral("advice"), record.advice);
        arr.append(obj);
    }

    QJsonObject root;
    root.insert(QStringLiteral("version"), 3);
    root.insert(QStringLiteral("records"), arr);
    DataStorage::writeJsonFile(QStringLiteral("training_records.json"), root);
}

int RecordsPage::lastCompositeScore() const
{
    return m_records.isEmpty() ? 0 : qBound(0, m_records.last().compositeScore, 100);
}

QString RecordsPage::lastLevelName() const
{
    return m_records.isEmpty() ? QStringLiteral("未评估") : m_records.last().level;
}

QString RecordsPage::lastLevelColor() const
{
    const int score = lastCompositeScore();
    if (score <= 0) return QStringLiteral("#A0A0A0");
    return ScoreEngine::levelColor(ScoreEngine::scoreToLevel(score));
}

QString RecordsPage::lastAdvice() const
{
    return m_records.isEmpty() ? QString() : m_records.last().advice;
}

void RecordsPage::rebuildSummaryRecord()
{
    if (!m_scoreLayout) {
        return;
    }

    const FontScale *fs = FontScale::instance();

    QLayoutItem *item = nullptr;
    while ((item = m_scoreLayout->takeAt(0)) != nullptr) {
        if (item->widget()) {
            delete item->widget();
        }
        delete item;
    }
    m_deleteChecks.clear();

    m_summary->setText(QStringLiteral("共 %1 次 L1/L2/L3/L4 综合训练记录；本页只保存“今日训练”页面产生的数据，评估结果不会写入训练记录。")
                       .arg(m_records.size()));

    QFrame *card = new QFrame(m_scoreContainer);
    card->setObjectName("summaryRecordCard");
    card->setMinimumHeight(360);
    card->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::MinimumExpanding);
    card->setStyleSheet(
        QStringLiteral(
            "QFrame#summaryRecordCard{background:#FFFFFF; border:1px solid #D0DDE8; border-radius:20px;}"
            "QLabel{background:transparent; border:none;}"
            "QCheckBox{background:transparent; border:none; font-size:%1px; color:#1A5276; font-weight:700;}"
            "QCheckBox::indicator{width:18px; height:18px;}")
            .arg(fs->px(14)));

    QVBoxLayout *cardLay = new QVBoxLayout(card);
    cardLay->setContentsMargins(22, 18, 22, 18);
    cardLay->setSpacing(12);

    QHBoxLayout *headerLay = new QHBoxLayout();
    headerLay->setSpacing(12);
    QLabel *cardTitle = new QLabel(QStringLiteral("训练综合得分记录"), card);
    cardTitle->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276;").arg(fs->px(22)));
    headerLay->addWidget(cardTitle, 1);

    QPushButton *selectAllBtn = new QPushButton(QStringLiteral("全选/取消"), card);
    selectAllBtn->setCursor(Qt::PointingHandCursor);
    selectAllBtn->setMinimumSize(fs->largeMode() ? 110 : 96, fs->largeMode() ? 42 : 36);
    selectAllBtn->setStyleSheet(
        QStringLiteral(
            "QPushButton{background:#FFFFFF; color:#1A5276; border:1px solid #BFD7EA; border-radius:10px;"
            "font-size:%1px; font-weight:800; padding:4px 12px;}"
            "QPushButton:hover{background:#E8F4FD;}")
            .arg(fs->px(14)));
    connect(selectAllBtn, &QPushButton::clicked, this, [this]() {
        bool shouldCheck = true;
        for (QCheckBox *cb : m_deleteChecks) {
            if (cb && !cb->isChecked()) {
                shouldCheck = true;
                break;
            }
            shouldCheck = false;
        }
        for (QCheckBox *cb : m_deleteChecks) {
            if (cb) cb->setChecked(shouldCheck);
        }
    });
    headerLay->addWidget(selectAllBtn, 0);

    QPushButton *deleteBtn = new QPushButton(QStringLiteral("删除选中历史记录"), card);
    deleteBtn->setCursor(Qt::PointingHandCursor);
    deleteBtn->setMinimumSize(fs->largeMode() ? 168 : 150, fs->largeMode() ? 42 : 36);
    deleteBtn->setStyleSheet(
        QStringLiteral(
            "QPushButton{background:#E74C3C; color:#FFFFFF; border:none; border-radius:10px;"
            "font-size:%1px; font-weight:900; padding:4px 14px;}"
            "QPushButton:hover{background:#C0392B;}"
            "QPushButton:pressed{background:#922B21;}")
            .arg(fs->px(14)));
    connect(deleteBtn, &QPushButton::clicked, this, &RecordsPage::deleteSelectedRecords);
    headerLay->addWidget(deleteBtn, 0);
    cardLay->addLayout(headerLay);

    QLabel *cardTip = new QLabel(QStringLiteral("仅显示第几次训练、L1/L2/L3/L4 综合训练包与综合得分；点击“综合得分”查看四个功能块的分项得分。"), card);
    cardTip->setStyleSheet(
        QStringLiteral("font-size:%1px; color:#606060;").arg(fs->px(14)));
    cardLay->addWidget(cardTip);

    if (m_records.isEmpty()) {
        QFrame *emptyBox = new QFrame(card);
        emptyBox->setObjectName("emptyRecordBox");
        emptyBox->setMinimumHeight(150);
        emptyBox->setStyleSheet("QFrame#emptyRecordBox{background:#F8FBFF; border:1px dashed #BFD7EA; border-radius:14px;}");
        QVBoxLayout *emptyLay = new QVBoxLayout(emptyBox);
        QLabel *emptyText = new QLabel(QStringLiteral("暂无历史训练记录"), emptyBox);
        emptyText->setAlignment(Qt::AlignCenter);
        emptyText->setStyleSheet(
            QStringLiteral("font-size:%1px; font-weight:900; color:#7F8C8D;").arg(fs->px(18)));
        emptyLay->addWidget(emptyText, 1);
        cardLay->addWidget(emptyBox, 1);
    } else {
        for (int i = 0; i < m_records.size(); ++i) {
            const TrainRecord &r = m_records.at(i);

            QFrame *row = new QFrame(card);
            row->setObjectName("scoreRow");
            row->setMinimumHeight(76);
            row->setStyleSheet(
                "QFrame#scoreRow{background:#F8FBFF; border:1px solid #E1EAF2; border-radius:14px;}"
                "QLabel{background:transparent; border:none;}"
            );
            QHBoxLayout *rowLay = new QHBoxLayout(row);
            rowLay->setContentsMargins(16, 10, 16, 10);
            rowLay->setSpacing(12);

            QCheckBox *selectBox = new QCheckBox(QStringLiteral("选择"), row);
            selectBox->setProperty("recordIndex", i);
            selectBox->setCursor(Qt::PointingHandCursor);
            m_deleteChecks.append(selectBox);
            rowLay->addWidget(selectBox, 0);

            QLabel *indexLabel = new QLabel(QStringLiteral("第%1次").arg(r.index), row);
            indexLabel->setMinimumWidth(78);
            indexLabel->setStyleSheet(
                QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276;").arg(fs->px(18)));
            rowLay->addWidget(indexLabel, 0);

            QLabel *actionLabel = new QLabel(QStringLiteral("%1    完成度 %2%").arg(r.actionName).arg(r.completion), row);
            actionLabel->setStyleSheet(
                QStringLiteral("font-size:%1px; color:#4A4A4A;").arg(fs->px(14)));
            actionLabel->setWordWrap(true);
            rowLay->addWidget(actionLabel, 1);

            QPushButton *scoreBtn = new QPushButton(QStringLiteral("综合得分  %1").arg(r.compositeScore), row);
            scoreBtn->setCursor(Qt::PointingHandCursor);
            scoreBtn->setMinimumSize(fs->largeMode() ? 168 : 150, fs->largeMode() ? 48 : 42);
            scoreBtn->setStyleSheet(
                QStringLiteral(
                    "QPushButton{background:#2E86C1; color:#FFFFFF; border:none; border-radius:12px;"
                    "font-size:%1px; font-weight:900; padding:6px 16px;}"
                    "QPushButton:hover{background:#1A5276;}"
                    "QPushButton:pressed{background:#154360;}")
                    .arg(fs->px(16)));
            connect(scoreBtn, &QPushButton::clicked, this, [this, i]() {
                showRecordDetail(i);
            });
            rowLay->addWidget(scoreBtn, 0);

            cardLay->addWidget(row);
        }
    }

    cardLay->addStretch(1);
    m_scoreLayout->addWidget(card);
    m_scoreLayout->addStretch(1);
}

void RecordsPage::deleteSelectedRecords()
{
    QVector<int> selectedIndexes;
    for (QCheckBox *cb : m_deleteChecks) {
        if (cb && cb->isChecked()) {
            selectedIndexes.append(cb->property("recordIndex").toInt());
        }
    }

    if (selectedIndexes.isEmpty()) {
        QMessageBox::information(this, QStringLiteral("提示"), QStringLiteral("请先勾选需要删除的历史记录。"));
        return;
    }

    if (QMessageBox::question(this,
                              QStringLiteral("确认删除"),
                              QStringLiteral("确定删除选中的 %1 条历史记录吗？").arg(selectedIndexes.size()),
                              QMessageBox::Yes | QMessageBox::No,
                              QMessageBox::No) != QMessageBox::Yes) {
        return;
    }

    std::sort(selectedIndexes.begin(), selectedIndexes.end(), std::greater<int>());
    for (int index : selectedIndexes) {
        if (index >= 0 && index < m_records.size()) {
            m_records.removeAt(index);
        }
    }

    saveStoredData();
    rebuildSummaryRecord();
}

void RecordsPage::showRecordDetail(int recordIndex)
{
    if (recordIndex < 0 || recordIndex >= m_records.size()) {
        return;
    }

    m_openDetailIndex = recordIndex;

    const TrainRecord &r = m_records.at(recordIndex);
    m_detailTitle->setText(QStringLiteral("第%1次训练详情").arg(r.index));
    m_detailMeta->setText(QStringLiteral("综合训练包：%1    完成度：%2%")
                          .arg(r.actionName)
                          .arg(r.completion));
    m_detailComposite->setText(QStringLiteral("综合得分\n%1").arg(r.compositeScore));
    m_detailLevel->setText(QStringLiteral("训练级别\n%1").arg(r.level));
    m_detailAdvice->setText(QStringLiteral("训练建议：%1").arg(r.advice));

    clearScoreGrid();
    for (int i = 0; i < r.blockNames.size() && i < r.blockScores.size(); ++i) {
        const QString blockName = r.blockNames.at(i).trimmed();
        addScoreRow(i, blockName.isEmpty()
                         ? QStringLiteral("功能块%1").arg(i + 1)
                         : blockName,
                    r.blockScores.at(i),
                    QStringLiteral("该功能块的完成质量评分"));
    }

    m_stack->setCurrentWidget(m_detailPage);
}

void RecordsPage::clearScoreGrid()
{
    if (!m_detailScoresGrid) {
        return;
    }

    QLayoutItem *item = nullptr;
    while ((item = m_detailScoresGrid->takeAt(0)) != nullptr) {
        if (item->widget()) {
            delete item->widget();
        }
        delete item;
    }
}

void RecordsPage::addScoreRow(int row, const QString &name, int score, const QString &desc)
{
    const FontScale *fs = FontScale::instance();
    QFrame *rowFrame = new QFrame(m_detailScoresPanel);
    rowFrame->setObjectName(QStringLiteral("detailScoreRow"));
    rowFrame->setMinimumHeight(118);
    rowFrame->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
    rowFrame->setStyleSheet(
        QStringLiteral(
            "QFrame#detailScoreRow{background:#F8FBFF; border:1px solid #E1EAF2; border-radius:14px;}"
            "QLabel{background:transparent; border:none;}"
            "QProgressBar{border:1px solid #D0DDE8; border-radius:8px; background:#EDF3F8;"
            "height:%1px; text-align:center; font-size:%2px; color:#1B2631; font-weight:800;}"
            "QProgressBar::chunk{background:#2E86C1; border-radius:8px;}")
            .arg(fs->largeMode() ? 22 : 18)
            .arg(fs->px(12)));

    QVBoxLayout *rowLay = new QVBoxLayout(rowFrame);
    rowLay->setContentsMargins(14, 12, 14, 12);
    rowLay->setSpacing(10);

    QHBoxLayout *topLay = new QHBoxLayout();
    topLay->setContentsMargins(0, 0, 0, 0);
    topLay->setSpacing(10);

    QLabel *nameLabel = new QLabel(name, rowFrame);
    nameLabel->setWordWrap(true);
    nameLabel->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
    nameLabel->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276; line-height:140%;")
            .arg(fs->px(14)));

    QLabel *valueLabel = new QLabel(QStringLiteral("%1\u5206").arg(score), rowFrame);
    valueLabel->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    valueLabel->setMinimumWidth(64);
    valueLabel->setSizePolicy(QSizePolicy::Minimum, QSizePolicy::Minimum);
    valueLabel->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#2E86C1;").arg(fs->px(15)));

    topLay->addWidget(nameLabel, 1);
    topLay->addWidget(valueLabel, 0);
    rowLay->addLayout(topLay);

    QProgressBar *bar = new QProgressBar(rowFrame);
    bar->setRange(0, 100);
    bar->setValue(score);
    bar->setFormat(QStringLiteral("%1\u5206").arg(score));
    bar->setFixedHeight(20);
    rowLay->addWidget(bar);

    QLabel *descLabel = new QLabel(desc, rowFrame);
    descLabel->setWordWrap(true);
    descLabel->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
    descLabel->setStyleSheet(
        QStringLiteral("font-size:%1px; color:#606060; line-height:140%;").arg(fs->px(12)));
    rowLay->addWidget(descLabel);

    m_detailScoresGrid->setVerticalSpacing(14);
    m_detailScoresGrid->addWidget(rowFrame, row, 0, 1, 3);
    m_detailScoresGrid->setColumnStretch(0, 1);
    m_detailScoresGrid->setColumnStretch(1, 1);
    m_detailScoresGrid->setColumnStretch(2, 1);
}
