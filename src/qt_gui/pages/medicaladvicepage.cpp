#include "medicaladvicepage.h"

#include "models/datastorage.h"
#include "utils/fontscale.h"

#include <QDateTime>
#include <QFrame>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QLayout>
#include <QPixmap>
#include <QProgressBar>
#include <QPushButton>
#include <QSizePolicy>
#include <QStringList>
#include <QtGlobal>

#include "widgets/radarchart.h"

QList<MedicalAdvicePage::DimensionAdvice> MedicalAdvicePage::allDimensionAdvices() const
{
    return {
        {
            QStringLiteral("range_of_motion"),
            QStringLiteral("抬举幅度"),
            QStringLiteral("权重 30%"),
            QStringLiteral("评估姿势：坐姿或站姿，身体保持直立，患侧手臂从体侧向前或向外缓慢抬高，记录最大可达角度与疼痛情况。"),
            QStringLiteral("低分可能原因：肩袖肌群损伤、肩峰撞击、冻结肩、肌肉拉伤、疼痛保护、长期制动导致关节僵硬。"),
            QStringLiteral("训练建议：墙面爬手、桌面滑行、钟摆运动、弹力带轻阻力外旋。"),
            QStringLiteral("若主要是疼痛影响，可在医生或药师指导下考虑对乙酰氨基酚、局部双氯芬酸凝胶；必要时短期使用布洛芬、萘普生、塞来昔布等 NSAIDs，并注意胃肠、肾功能和心血管风险。"),
            QStringLiteral("若活动度明显受限、夜间痛或怀疑冻结肩/肩袖撕裂，应建议骨科或康复科就医。医生可能安排影像检查、系统物理治疗，或根据病因考虑肩关节腔糖皮质激素注射等处理。"),
            QStringLiteral(":/res/pic/rehab_advice/exercise_pendulum_exercise.png"),
            QStringLiteral("钟摆运动/肩部活动度恢复"),
            QStringLiteral(":/res/pic/rehab_advice/med_diclofenac_topical_gel.png"),
            QStringLiteral("双氯芬酸凝胶：局部止痛抗炎方向")
        },
        {
            QStringLiteral("smoothness"),
            QStringLiteral("运动平滑度"),
            QStringLiteral("权重 25%"),
            QStringLiteral("评估姿势：双手自然下垂后，手心朝外做侧平举并举过头顶，观察抬举幅度、左右对称与动作平稳度。"),
            QStringLiteral("低分可能原因：肩胛控制不足、肌肉协调性差、疼痛导致动作保护、神经控制异常、痉挛或肌张力异常。"),
            QStringLiteral("训练建议：桌面直线滑动、画圆/画 8 字、节拍器匀速训练、端杯慢速移动。"),
            QStringLiteral("若卡顿由疼痛造成，可按疼痛方向提示常规止痛/抗炎药物；若伴明显肌肉紧张、痉挛，应提示医生评估是否需要肌松或抗痉挛药物。"),
            QStringLiteral("若出现明显不受控、僵硬、痉挛或神经损伤表现，应建议康复科/神经科评估。医生可能根据情况考虑巴氯芬、替扎尼定等抗痉挛药，局灶性痉挛可评估肉毒毒素 A 注射。"),
            QStringLiteral(":/res/pic/rehab_advice/exercise_essential_tremor_spiral.png"),
            QStringLiteral("侧平举过顶评估"),
            QStringLiteral(":/res/pic/rehab_advice/med_baclofen.png"),
            QStringLiteral("巴氯芬：医生评估抗痉挛方向")
        },
        {
            QStringLiteral("tremor"),
            QStringLiteral("震颤程度"),
            QStringLiteral("权重 20%"),
            QStringLiteral("评估姿势：端杯、指鼻或目标触碰评估，前臂可先支撑在桌面上，再逐步改为无支撑，观察手部稳定性和目标命中情况。"),
            QStringLiteral("低分可能原因：疲劳、紧张焦虑、疼痛诱发抖动、药物副作用、特发性震颤、帕金森样问题或其他神经系统异常。"),
            QStringLiteral("训练建议：前臂支撑端杯、轻重量等长保持、指鼻训练、呼吸放松训练。"),
            QStringLiteral("轻中度震颤不建议软件直接推荐抗震颤药。可提示减少咖啡因、保证休息、排查药物副作用；若由疼痛诱发，可按疼痛处理方向提示。"),
            QStringLiteral("若震颤明显影响日常生活，应建议神经内科评估。若确认为特发性震颤，医生可能考虑普萘洛尔或扑米酮等药物；心率慢、哮喘、低血压、肝肾问题等人群需谨慎。"),
            QStringLiteral(":/res/pic/rehab_advice/exercise_grip_strength_stability.png"),
            QStringLiteral("握力稳定/端持训练参考"),
            QStringLiteral(":/res/pic/rehab_advice/med_propranolol.png"),
            QStringLiteral("普萘洛尔：神经内科评估方向")
        },
        {
            QStringLiteral("symmetry"),
            QStringLiteral("双侧对称性"),
            QStringLiteral("权重 15%"),
            QStringLiteral("评估姿势：双臂同步前举/外展评估，双手同时抬起，比较左右臂角度、速度、稳定性和肩胛代偿。"),
            QStringLiteral("低分可能原因：单侧肌力不足、单侧疼痛、肩胛代偿、偏瘫后运动控制差、关节活动度不一致。"),
            QStringLiteral("训练建议：双手抱棍前举、镜像训练、双侧弹力带划船、双手推墙。"),
            QStringLiteral("若不对称主要由单侧疼痛导致，可提示常规止痛/抗炎方向；若伴肌肉紧张或痉挛，应提示医生评估抗痉挛治疗。"),
            QStringLiteral("若一侧明显无力、麻木、动作偏斜或疑似神经系统问题，应建议神经科/康复科评估。中风后或神经损伤后应以重复任务训练、镜像训练、肌力训练和痉挛管理为重点。"),
            QStringLiteral(":/res/pic/rehab_advice/exercise_wall_pushup.png"),
            QStringLiteral("双手推墙/双侧同步训练"),
            QStringLiteral(":/res/pic/rehab_advice/med_ibuprofen.png"),
            QStringLiteral("布洛芬：疼痛抗炎方向")
        },
        {
            QStringLiteral("speed"),
            QStringLiteral("运动速度"),
            QStringLiteral("权重 5%"),
            QStringLiteral("评估姿势：计时触靶/定时前举评估，在规定时间内完成目标触碰或前举动作，记录完成时间和动作质量。"),
            QStringLiteral("低分可能原因：疼痛、肌力不足、关节僵硬、神经反应慢、动作恐惧、疲劳或协调性不足。"),
            QStringLiteral("训练建议：节拍器节律训练、低阻力快速触靶、定时前举、弹力带低阻力重复屈伸，强调质量优先。"),
            QStringLiteral("若速度慢由疼痛或炎症导致，可提示局部 NSAIDs、对乙酰氨基酚或短期口服 NSAIDs。不要用“兴奋剂”或不明补剂来提高动作速度。"),
            QStringLiteral("若速度突然下降，或伴麻木、无力、头晕、说话不清等情况，应暂停训练并立即就医。若由肩袖损伤或严重疼痛造成，需要明确病因，而不是单纯加止痛药。"),
            QStringLiteral(":/res/pic/rehab_advice/exercise_overhead_press_arm_raise.png"),
            QStringLiteral("前举/上举节律训练参考"),
            QStringLiteral(":/res/pic/rehab_advice/med_acetaminophen.png"),
            QStringLiteral("对乙酰氨基酚：短期止痛方向")
        },
        {
            QStringLiteral("fatigue"),
            QStringLiteral("运动耐力"),
            QStringLiteral("权重 5%"),
            QStringLiteral("评估姿势：重复前举/保持动作评估，连续完成多次前举或维持指定姿势，记录疲劳出现时间和动作质量下降情况。"),
            QStringLiteral("低分可能原因：肌肉耐力不足、长期制动、疼痛、心肺耐力差、睡眠不足、贫血、营养或内分泌问题。"),
            QStringLiteral("训练建议：分组重复前举、30 秒等长保持、低强度弹力带循环、间歇训练，避免一次性过量。"),
            QStringLiteral("若疼痛限制耐力，可提示常规止痛/抗炎方向。若只是疲劳，不建议自行服用激素、兴奋剂或所谓“强效补药”。"),
            QStringLiteral("若轻微活动即明显疲劳、胸闷、心慌、头晕，应停止训练并就医。若检查提示贫血、维生素 D/B12 缺乏、营养不足或内分泌问题，应按检查结果进行针对性治疗。"),
            QStringLiteral(":/res/pic/rehab_advice/exercise_biceps_curl_repetition.png"),
            QStringLiteral("分组重复/低阻力耐力训练"),
            QStringLiteral(":/res/pic/rehab_advice/med_naproxen.png"),
            QStringLiteral("萘普生：NSAIDs 抗炎方向")
        }
    };
}

MedicalAdvicePage::MedicalAdvicePage(QWidget *parent) : QWidget(parent)
{
    setupUI();
    loadStoredRecords();
    rebuildRecordList();
}

void MedicalAdvicePage::setupUI()
{
    QVBoxLayout *root = new QVBoxLayout(this);
    root->setContentsMargins(24, 16, 24, 12);
    root->setSpacing(0);

    m_stack = new QStackedWidget(this);
    m_stack->setStyleSheet("QStackedWidget{background:transparent; border:none;}");
    root->addWidget(m_stack, 1);

    buildListPage();
    buildDetailPage();
    buildDimensionDetailPage();
    m_stack->setCurrentWidget(m_listPage);
}

void MedicalAdvicePage::buildListPage()
{
    m_listPage = new QWidget(this);
    m_listPage->setStyleSheet("background:transparent; border:none;");

    QVBoxLayout *lay = new QVBoxLayout(m_listPage);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->setSpacing(12);

    QLabel *title = new QLabel(QStringLiteral("医疗建议记录"), m_listPage);
    m_listTitle = title;
    title->setStyleSheet("font-size:24px; font-weight:900; color:#1A5276; border:none;");
    lay->addWidget(title);

    m_recordSummary = new QLabel(m_listPage);
    m_recordSummary->setStyleSheet("font-size:14px; color:#606060; border:none;");
    lay->addWidget(m_recordSummary);

    m_recordScrollArea = new QScrollArea(m_listPage);
    m_recordScrollArea->setWidgetResizable(true);
    m_recordScrollArea->setStyleSheet("QScrollArea{border:none; background:transparent;}");

    m_recordContainer = new QWidget(m_recordScrollArea);
    m_recordContainer->setStyleSheet("background:transparent; border:none;");
    m_recordLayout = new QVBoxLayout(m_recordContainer);
    m_recordLayout->setContentsMargins(0, 0, 0, 0);
    m_recordLayout->setSpacing(12);

    m_recordScrollArea->setWidget(m_recordContainer);
    lay->addWidget(m_recordScrollArea, 1);

    m_stack->addWidget(m_listPage);
}

void MedicalAdvicePage::buildDetailPage()
{
    m_detailPage = new QWidget(this);
    m_detailPage->setStyleSheet("background:transparent; border:none;");

    QVBoxLayout *lay = new QVBoxLayout(m_detailPage);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->setSpacing(12);

    QPushButton *backBtn = new QPushButton(QStringLiteral("返回记录列表"), m_detailPage);
    backBtn->setCursor(Qt::PointingHandCursor);
    backBtn->setStyleSheet(
        "QPushButton{background:#FFFFFF; color:#1A5276; border:1px solid #C8D8E8; border-radius:10px;"
        "font-size:14px; font-weight:bold; padding:4px 16px;}"
        "QPushButton:hover{background:#E8F4FD;}"
        "QPushButton:pressed{background:#D6EAF8;}"
    );
    connect(backBtn, &QPushButton::clicked, this, [this]() {
        rebuildRecordList();
        m_stack->setCurrentWidget(m_listPage);
    });
    lay->addWidget(backBtn, 0, Qt::AlignLeft);

    m_detailScrollArea = new QScrollArea(m_detailPage);
    m_detailScrollArea->setWidgetResizable(true);
    m_detailScrollArea->setStyleSheet("QScrollArea{border:none; background:transparent;}");

    m_detailContent = new QWidget(m_detailScrollArea);
    m_detailContent->setStyleSheet("background:transparent; border:none;");
    m_detailLayout = new QVBoxLayout(m_detailContent);
    m_detailLayout->setContentsMargins(0, 0, 0, 0);
    m_detailLayout->setSpacing(14);

    m_detailScrollArea->setWidget(m_detailContent);
    lay->addWidget(m_detailScrollArea, 1);

    m_stack->addWidget(m_detailPage);
}

void MedicalAdvicePage::buildDimensionDetailPage()
{
    m_dimensionPage = new QWidget(this);
    m_dimensionPage->setStyleSheet("background:transparent; border:none;");

    QVBoxLayout *lay = new QVBoxLayout(m_dimensionPage);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->setSpacing(12);

    QPushButton *backBtn = new QPushButton(QStringLiteral("返回本次评估详情"), m_dimensionPage);
    backBtn->setCursor(Qt::PointingHandCursor);
    backBtn->setStyleSheet(
        "QPushButton{background:#FFFFFF; color:#1A5276; border:1px solid #C8D8E8; border-radius:10px;"
        "font-size:14px; font-weight:bold; padding:4px 16px;}"
        "QPushButton:hover{background:#E8F4FD;}"
        "QPushButton:pressed{background:#D6EAF8;}"
    );
    connect(backBtn, &QPushButton::clicked, this, [this]() {
        if (m_currentRecordStorageIndex >= 0 && m_currentRecordStorageIndex < m_records.size()) {
            rebuildDetailPage(m_records.at(m_currentRecordStorageIndex), m_currentRecordStorageIndex);
        }
        m_stack->setCurrentWidget(m_detailPage);
    });
    lay->addWidget(backBtn, 0, Qt::AlignLeft);

    m_dimensionScrollArea = new QScrollArea(m_dimensionPage);
    m_dimensionScrollArea->setWidgetResizable(true);
    m_dimensionScrollArea->setStyleSheet("QScrollArea{border:none; background:transparent;}");

    m_dimensionContent = new QWidget(m_dimensionScrollArea);
    m_dimensionContent->setStyleSheet("background:transparent; border:none;");
    m_dimensionLayout = new QVBoxLayout(m_dimensionContent);
    m_dimensionLayout->setContentsMargins(0, 0, 0, 0);
    m_dimensionLayout->setSpacing(14);

    m_dimensionScrollArea->setWidget(m_dimensionContent);
    lay->addWidget(m_dimensionScrollArea, 1);

    m_stack->addWidget(m_dimensionPage);
}

void MedicalAdvicePage::setLatestAssessment(const ScoreResult &result)
{
    ScoreResult stored = result;
    if (!stored.timestamp.isValid()) {
        stored.timestamp = QDateTime::currentDateTime();
    }
    if (stored.source.isEmpty()) {
        stored.source = QStringLiteral("assessment");
    }
    DataStorage::saveLatestAssessment(stored);

    if (!m_records.isEmpty()) {
        MedicalAdviceRecord &last = m_records.last();
        // 训练后仅综合分变化、六维不变：更新最后一条记录，不新增条目。
        if (ScoreEngine::assessmentDimensionsEqual(last.result, stored)) {
            last.result.compositeScore = stored.compositeScore;
            last.result.level = stored.level;
            last.result.levelName = stored.levelName;
            last.result.levelColor = stored.levelColor;
            if (!stored.advice.isEmpty()) {
                last.result.advice = stored.advice;
            }
            saveStoredRecords();
            rebuildRecordList();
            return;
        }
        // 同一条评估结果被外部信号重复推送，覆盖最后一条，避免列表出现重复记录。
        if (last.result.timestamp == stored.timestamp
                && last.result.compositeScore == stored.compositeScore) {
            last.result = stored;
            saveStoredRecords();
            rebuildRecordList();
            return;
        }
    }

    MedicalAdviceRecord record;
    record.index = m_records.isEmpty() ? 1 : (m_records.last().index + 1);
    record.result = stored;
    m_records.append(record);
    saveStoredRecords();
    rebuildRecordList();
}

void MedicalAdvicePage::refresh()
{
    rebuildRecordList();
    if (m_stack && m_stack->currentWidget() != m_detailPage && m_stack->currentWidget() != m_dimensionPage) {
        m_stack->setCurrentWidget(m_listPage);
    }
}

void MedicalAdvicePage::applyFontScale()
{
    const FontScale *fs = FontScale::instance();
    if (m_listTitle) {
        m_listTitle->setStyleSheet(
            QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276; border:none;")
                .arg(fs->px(24)));
    }
    if (m_recordSummary) {
        m_recordSummary->setStyleSheet(
            QStringLiteral("font-size:%1px; color:#606060; border:none;")
                .arg(fs->px(14)));
    }

    if (!m_stack) {
        return;
    }
    QWidget *current = m_stack->currentWidget();
    if (current == m_dimensionPage && m_currentRecordStorageIndex >= 0
        && !m_currentDimensionKey.isEmpty()) {
        showDimensionDetail(m_currentRecordStorageIndex, m_currentDimensionKey);
    } else if (current == m_detailPage && m_currentRecordStorageIndex >= 0) {
        showRecordDetail(m_currentRecordStorageIndex);
    } else {
        rebuildRecordList();
    }
}

void MedicalAdvicePage::clearLayout(QLayout *layout)
{
    if (!layout) {
        return;
    }
    QLayoutItem *item = nullptr;
    while ((item = layout->takeAt(0)) != nullptr) {
        if (item->layout()) {
            clearLayout(item->layout());
            delete item->layout();
        }
        if (item->widget()) {
            delete item->widget();
        }
        delete item;
    }
}

void MedicalAdvicePage::loadStoredRecords()
{
    if (m_recordsLoaded) {
        return;
    }
    m_recordsLoaded = true;
    m_records.clear();

    QJsonObject root;
    if (!DataStorage::readJsonFile(QStringLiteral("medical_advice_records.json"), &root)) {
        return;
    }

    const QJsonArray arr = root.value(QStringLiteral("records")).toArray();
    for (const QJsonValue &value : arr) {
        const QJsonObject obj = value.toObject();
        if (obj.isEmpty()) {
            continue;
        }

        MedicalAdviceRecord record;
        record.index = obj.value(QStringLiteral("index")).toInt(m_records.size() + 1);
        record.result = DataStorage::scoreResultFromJson(obj.value(QStringLiteral("result")).toObject());
        if (record.result.levelName.isEmpty()) {
            record.result.levelName = ScoreEngine::levelName(ScoreEngine::scoreToLevel(record.result.compositeScore));
        }
        if (record.result.levelColor.isEmpty()) {
            record.result.levelColor = ScoreEngine::levelColor(ScoreEngine::scoreToLevel(record.result.compositeScore));
        }
        if (record.result.advice.isEmpty() && record.result.compositeScore > 0) {
            record.result.advice = ScoreEngine::randomAdviceForScore(record.result.compositeScore);
        }
        m_records.append(record);
    }
}

void MedicalAdvicePage::saveStoredRecords() const
{
    QJsonArray arr;
    for (const MedicalAdviceRecord &record : m_records) {
        QJsonObject obj;
        obj.insert(QStringLiteral("index"), record.index);
        obj.insert(QStringLiteral("result"), DataStorage::scoreResultToJson(record.result));
        arr.append(obj);
    }

    QJsonObject root;
    root.insert(QStringLiteral("version"), 1);
    root.insert(QStringLiteral("records"), arr);
    DataStorage::writeJsonFile(QStringLiteral("medical_advice_records.json"), root);
}

void MedicalAdvicePage::rebuildRecordList()
{
    clearLayout(m_recordLayout);
    if (!m_recordSummary || !m_recordLayout) {
        return;
    }

    const FontScale *fs = FontScale::instance();

    m_recordSummary->setText(QStringLiteral("共 %1 次评估医疗建议记录；最近一次评估记录排在最上方。")
                             .arg(m_records.size()));

    if (m_records.isEmpty()) {
        QFrame *emptyBox = new QFrame(m_recordContainer);
        emptyBox->setObjectName("emptyMedicalRecordBox");
        emptyBox->setMinimumHeight(180);
        emptyBox->setStyleSheet(
            "QFrame#emptyMedicalRecordBox{background:#F8FBFF; border:1px dashed #BFD7EA; border-radius:16px;}"
            "QLabel{background:transparent; border:none;}"
        );
        QVBoxLayout *emptyLay = new QVBoxLayout(emptyBox);
        emptyLay->setContentsMargins(18, 18, 18, 18);
        QLabel *emptyText = new QLabel(QStringLiteral("暂无医疗建议记录\n请先进入“评估”页面完成一次六维评估。"), emptyBox);
        emptyText->setAlignment(Qt::AlignCenter);
        emptyText->setStyleSheet(
            QStringLiteral("font-size:%1px; font-weight:900; color:#7F8C8D; line-height:150%;")
                .arg(fs->px(18)));
        emptyLay->addWidget(emptyText, 1);
        m_recordLayout->addWidget(emptyBox);
        m_recordLayout->addStretch(1);
        return;
    }

    for (int i = m_records.size() - 1; i >= 0; --i) {
        const MedicalAdviceRecord &record = m_records.at(i);
        const int composite = qBound(0, record.result.compositeScore, 100);
        const QString levelName = record.result.levelName.isEmpty()
                ? ScoreEngine::levelName(ScoreEngine::scoreToLevel(composite))
                : record.result.levelName;
        const QString levelColor = record.result.levelColor.isEmpty()
                ? ScoreEngine::levelColor(ScoreEngine::scoreToLevel(composite))
                : record.result.levelColor;

        QFrame *row = new QFrame(m_recordContainer);
        row->setObjectName("medicalAdviceRecordRow");
        row->setMinimumHeight(92);
        row->setStyleSheet(
            "QFrame#medicalAdviceRecordRow{background:#FFFFFF; border:1px solid #D0DDE8; border-radius:18px;}"
            "QLabel{background:transparent; border:none;}"
        );
        QHBoxLayout *rowLay = new QHBoxLayout(row);
        rowLay->setContentsMargins(18, 14, 18, 14);
        rowLay->setSpacing(14);

        QVBoxLayout *leftLay = new QVBoxLayout();
        leftLay->setSpacing(6);
        QLabel *recordTitle = new QLabel(QStringLiteral("第%1次评估医疗建议").arg(record.index), row);
        recordTitle->setStyleSheet(
            QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276;").arg(fs->px(20)));
        leftLay->addWidget(recordTitle);

        QLabel *recordMeta = new QLabel(QStringLiteral("评估结果：%1    点开后可查看综合建议、六维建议概览以及每个维度的独立分析。")
                                        .arg(levelName), row);
        recordMeta->setWordWrap(true);
        recordMeta->setStyleSheet(
            QStringLiteral("font-size:%1px; color:#606060;").arg(fs->px(14)));
        leftLay->addWidget(recordMeta);
        rowLay->addLayout(leftLay, 1);

        QLabel *scoreBadge = new QLabel(QStringLiteral("综合得分\n%1分").arg(composite), row);
        scoreBadge->setAlignment(Qt::AlignCenter);
        scoreBadge->setMinimumSize(fs->largeMode() ? 132 : 118, fs->largeMode() ? 72 : 62);
        scoreBadge->setStyleSheet(QString(
            "background:#F8FBFF; color:%1; border:1px solid #D0DDE8; border-radius:14px;"
            "font-size:%2px; font-weight:900; padding:6px;"
        ).arg(levelColor).arg(fs->px(18)));
        rowLay->addWidget(scoreBadge, 0);

        QPushButton *detailBtn = new QPushButton(QStringLiteral("查看建议"), row);
        detailBtn->setCursor(Qt::PointingHandCursor);
        detailBtn->setMinimumSize(fs->largeMode() ? 126 : 112, fs->largeMode() ? 48 : 42);
        detailBtn->setStyleSheet(
            QStringLiteral(
                "QPushButton{background:#2E86C1; color:#FFFFFF; border:none; border-radius:12px;"
                "font-size:%1px; font-weight:900; padding:6px 14px;}"
                "QPushButton:hover{background:#1A5276;}"
                "QPushButton:pressed{background:#154360;}")
                .arg(fs->px(15)));
        connect(detailBtn, &QPushButton::clicked, this, [this, i]() {
            showRecordDetail(i);
        });
        rowLay->addWidget(detailBtn, 0);

        m_recordLayout->addWidget(row);
    }
    m_recordLayout->addStretch(1);
}

void MedicalAdvicePage::showRecordDetail(int recordStorageIndex)
{
    if (recordStorageIndex < 0 || recordStorageIndex >= m_records.size()) {
        return;
    }
    m_currentRecordStorageIndex = recordStorageIndex;
    rebuildDetailPage(m_records.at(recordStorageIndex), recordStorageIndex);
    if (m_stack) {
        m_stack->setCurrentWidget(m_detailPage);
    }
}

void MedicalAdvicePage::showDimensionDetail(int recordStorageIndex, const QString &dimensionKey)
{
    if (recordStorageIndex < 0 || recordStorageIndex >= m_records.size()) {
        return;
    }

    const QList<DimensionAdvice> advices = allDimensionAdvices();
    for (const DimensionAdvice &advice : advices) {
        if (advice.key == dimensionKey) {
            m_currentRecordStorageIndex = recordStorageIndex;
            m_currentDimensionKey = dimensionKey;
            rebuildDimensionDetailPage(m_records.at(recordStorageIndex), advice);
            if (m_stack) {
                m_stack->setCurrentWidget(m_dimensionPage);
            }
            return;
        }
    }
}

int MedicalAdvicePage::dimensionScore(const ScoreResult &result, const QString &key) const
{
    return ScoreEngine::dimensionDisplayPercent(result, key);
}

QString MedicalAdvicePage::scoreStatusText(int score) const
{
    if (score > 80) {
        return QStringLiteral("表现较好");
    }
    if (score >= 50) {
        return QStringLiteral("轻中度不足");
    }
    return QStringLiteral("明显异常或风险较高");
}

QString MedicalAdvicePage::scoreStatusColor(int score) const
{
    if (score > 80) {
        return QStringLiteral("#27AE60");
    }
    if (score >= 50) {
        return QStringLiteral("#F39C12");
    }
    return QStringLiteral("#E74C3C");
}

QString MedicalAdvicePage::overallAdviceForScore(int score) const
{
    if (score > 80) {
        return QStringLiteral("当前综合评分表现较好，建议继续进行康复训练。训练时保持动作缓慢、稳定、对称，在无明显疼痛的前提下逐步增加次数、保持时间或动作质量要求。重点从单纯完成动作转向稳定性、对称性和耐力巩固。");
    }
    if (score >= 50) {
        return QStringLiteral("当前综合评分存在轻中度不足，建议降低训练强度，增加热身、拉伸和低负荷重复训练，优先选择可控制、无明显疼痛的动作。若某一维度持续偏低，应减少难度并复查动作姿势与传感器佩戴情况。");
    }
    return QStringLiteral("当前综合评分明显偏低，不建议自行加大训练量。若伴明显疼痛、麻木、震颤、单侧无力、活动范围突然下降、胸闷心慌等情况，应停止训练并尽快到骨科、康复科或神经内科评估。");
}

QString MedicalAdvicePage::dimensionMedicineText(const DimensionAdvice &advice, int score) const
{
    if (score > 80) {
        return QStringLiteral("医疗建议/建议药物方向：该维度表现较好，一般不主动推荐药物；若有轻微酸痛，优先休息、热身、放松和动作调整。");
    }
    if (score >= 50) {
        return QStringLiteral("医疗建议/建议药物方向：%1").arg(advice.medicineMid);
    }
    return QStringLiteral("医疗建议/建议药物方向：%1").arg(advice.severeAdvice);
}

QString MedicalAdvicePage::dimensionBriefSuggestion(const DimensionAdvice &advice, int score) const
{
    if (score > 80) {
        return QStringLiteral("维持强化建议：%1 在无明显疼痛的前提下逐步增加动作质量要求，继续关注动作稳定性和对称性。")
                .arg(advice.training);
    }
    if (score >= 50) {
        return QStringLiteral("轻中度不足建议：先降低训练强度，优先执行该维度的低负荷训练；若伴疼痛或紧张，参考对应医疗建议。%1")
                .arg(advice.training);
    }
    return QStringLiteral("明显低分建议：暂缓高强度训练，优先明确低分原因并就医评估。%1")
            .arg(advice.severeAdvice);
}

QString MedicalAdvicePage::dimensionAnalysisText(const DimensionAdvice &advice, int score) const
{
    if (score > 80) {
        return QStringLiteral("该维度得分较高，说明当前动作质量相对稳定。软件建议以巩固训练为主，不急于增加负荷，可把训练重点放在动作标准化、左右协调和持续稳定性上。若训练后出现轻微酸胀，优先通过休息、热身和动作调整处理。");
    }
    if (score >= 50) {
        return QStringLiteral("该维度存在轻中度不足，常见处理方式是降低训练速度和强度，增加热身与拉伸，并将动作拆分为低负荷、可控制的小步骤。若连续多次评估仍偏低，需要结合低分原因检查动作姿势、疼痛情况和传感器佩戴稳定性。");
    }
    return QStringLiteral("该维度明显偏低，提示动作完成质量或安全风险需要重点关注。建议暂停该方向的高强度训练，不要单纯依靠加大训练量或自行用药来提高评分；若伴随明显疼痛、麻木、无力、震颤或活动范围突然下降，应及时到相关科室评估。");
}

void MedicalAdvicePage::rebuildDetailPage(const MedicalAdviceRecord &record, int recordStorageIndex)
{
    clearLayout(m_detailLayout);

    const FontScale *fs = FontScale::instance();
    const ScoreResult &result = record.result;
    const int composite = qBound(0, result.compositeScore, 100);
    const QString levelName = result.levelName.isEmpty()
            ? ScoreEngine::levelName(ScoreEngine::scoreToLevel(composite))
            : result.levelName;
    const QString levelColor = result.levelColor.isEmpty()
            ? ScoreEngine::levelColor(ScoreEngine::scoreToLevel(composite))
            : result.levelColor;

    QLabel *title = new QLabel(QStringLiteral("第%1次评估医疗建议详情").arg(record.index), m_detailContent);
    title->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276; border:none;").arg(fs->px(24)));
    m_detailLayout->addWidget(title);

    QFrame *summaryCard = new QFrame(m_detailContent);
    summaryCard->setObjectName("medicalSummaryCard");
    summaryCard->setStyleSheet(
        "QFrame#medicalSummaryCard{background:#FFFFFF; border:1px solid #D0DDE8; border-radius:18px;}"
        "QLabel{border:none; background:transparent;}"
    );
    QHBoxLayout *summaryLay = new QHBoxLayout(summaryCard);
    summaryLay->setContentsMargins(20, 18, 20, 18);
    summaryLay->setSpacing(18);

    QVBoxLayout *leftLay = new QVBoxLayout();
    leftLay->setSpacing(10);
    QLabel *summaryTitle = new QLabel(QStringLiteral("本次评估结果"), summaryCard);
    summaryTitle->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276;").arg(fs->px(20)));
    leftLay->addWidget(summaryTitle);

    QLabel *scoreBadge = new QLabel(QStringLiteral("%1分").arg(composite), summaryCard);
    scoreBadge->setAlignment(Qt::AlignCenter);
    scoreBadge->setMinimumSize(fs->largeMode() ? 168 : 150, fs->largeMode() ? 98 : 88);
    scoreBadge->setStyleSheet(QString(
        "background:#E8F4FD; color:%1; border:1px solid #BFD7EA; border-radius:16px;"
        "font-size:%2px; font-weight:900; padding:8px;"
    ).arg(levelColor).arg(fs->px(30)));
    leftLay->addWidget(scoreBadge);

    QLabel *levelBadge = new QLabel(levelName, summaryCard);
    levelBadge->setAlignment(Qt::AlignCenter);
    levelBadge->setMinimumHeight(fs->largeMode() ? 48 : 42);
    levelBadge->setStyleSheet(QString(
        "background:#F8FBFF; color:%1; border:1px solid #D0DDE8; border-radius:12px;"
        "font-size:%2px; font-weight:800; padding:6px;"
    ).arg(levelColor).arg(fs->px(16)));
    leftLay->addWidget(levelBadge);
    leftLay->addStretch(1);
    summaryLay->addLayout(leftLay, 0);

    QVBoxLayout *adviceLay = new QVBoxLayout();
    adviceLay->setSpacing(10);
    QLabel *overallTitle = new QLabel(QStringLiteral("总体评分建议"), summaryCard);
    overallTitle->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276;").arg(fs->px(18)));
    adviceLay->addWidget(overallTitle);

    QLabel *overallAdvice = new QLabel(summaryCard);
    overallAdvice->setWordWrap(true);
    overallAdvice->setText(QStringLiteral("总体建议：%1\n系统随机建议：%2")
                           .arg(overallAdviceForScore(composite),
                                result.advice.isEmpty() ? ScoreEngine::randomAdviceForScore(composite) : result.advice));
    overallAdvice->setStyleSheet(
        QStringLiteral(
            "background:#F8FBFF; color:#34495E; border:1px solid #E1EAF2; border-radius:12px;"
            "font-size:%1px; line-height:150%; padding:10px;")
            .arg(fs->px(14)));
    adviceLay->addWidget(overallAdvice);
    summaryLay->addLayout(adviceLay, 1);

    QVBoxLayout *radarLay = new QVBoxLayout();
    radarLay->setSpacing(6);
    QLabel *radarTitle = new QLabel(QStringLiteral("六维评估图"), summaryCard);
    radarTitle->setAlignment(Qt::AlignCenter);
    radarTitle->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276;").arg(fs->px(16)));
    radarLay->addWidget(radarTitle);

    RadarChart *radar = new RadarChart(summaryCard);
    radar->setMinimumSize(280, 260);
    radar->setDimensions({QStringLiteral("抬举幅度"), QStringLiteral("运动平滑度"), QStringLiteral("震颤程度"), QStringLiteral("双侧对称性"), QStringLiteral("运动速度"), QStringLiteral("运动耐力")});
    radar->setValues(result.dims);
    radarLay->addWidget(radar, 1, Qt::AlignCenter);
    summaryLay->addLayout(radarLay, 1);

    m_detailLayout->addWidget(summaryCard);

    QLabel *dimTitle = new QLabel(QStringLiteral("六个维度对应建议"), m_detailContent);
    dimTitle->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276; border:none; margin-top:4px;")
            .arg(fs->px(20)));
    m_detailLayout->addWidget(dimTitle);

    const QList<DimensionAdvice> advices = allDimensionAdvices();
    for (const DimensionAdvice &advice : advices) {
        m_detailLayout->addWidget(createDimensionOverviewCard(advice, result, recordStorageIndex, m_detailContent));
    }

    QLabel *safeTip = new QLabel(QStringLiteral("用药安全提示：对乙酰氨基酚、布洛芬、萘普生、塞来昔布、双氯芬酸等药物不宜自行叠加；胃溃疡、肾功能异常、高血压、心血管疾病、哮喘、正在使用抗凝药、孕期或肝功能异常人群需先咨询医生。巴氯芬、替扎尼定、普萘洛尔、扑米酮、肉毒毒素 A、糖皮质激素注射等只能作为医生可能评估的治疗方向。"), m_detailContent);
    safeTip->setWordWrap(true);
    safeTip->setStyleSheet(
        QStringLiteral(
            "background:#FFF5F5; color:#8A1F11; border:1px solid #F5C6CB; border-radius:12px;"
            "font-size:%1px; line-height:150%; padding:10px;")
            .arg(fs->px(13)));
    m_detailLayout->addWidget(safeTip);
    m_detailLayout->addStretch(1);
}

void MedicalAdvicePage::rebuildDimensionDetailPage(const MedicalAdviceRecord &record, const DimensionAdvice &advice)
{
    clearLayout(m_dimensionLayout);

    const FontScale *fs = FontScale::instance();
    const ScoreResult &result = record.result;
    const int score = dimensionScore(result, advice.key);
    const QString scoreDetail = ScoreEngine::dimensionScoreLabel(result, advice.key);
    const int composite = qBound(0, result.compositeScore, 100);
    const QString status = scoreStatusText(score);
    const QString statusColor = scoreStatusColor(score);

    QLabel *title = new QLabel(QStringLiteral("第%1次评估 · %2独立分析").arg(record.index).arg(advice.name), m_dimensionContent);
    title->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276; border:none;").arg(fs->px(24)));
    m_dimensionLayout->addWidget(title);

    QFrame *evalCard = new QFrame(m_dimensionContent);
    evalCard->setObjectName("dimensionEvalCard");
    evalCard->setStyleSheet(
        "QFrame#dimensionEvalCard{background:#FFFFFF; border:1px solid #D0DDE8; border-radius:18px;}"
        "QLabel{border:none; background:transparent;}"
    );
    QHBoxLayout *evalLay = new QHBoxLayout(evalCard);
    evalLay->setContentsMargins(20, 18, 20, 18);
    evalLay->setSpacing(18);

    QLabel *scoreBadge = new QLabel(QStringLiteral("%1\n%2").arg(advice.name, scoreDetail), evalCard);
    scoreBadge->setAlignment(Qt::AlignCenter);
    scoreBadge->setMinimumSize(fs->largeMode() ? 188 : 170, fs->largeMode() ? 112 : 100);
    scoreBadge->setStyleSheet(QString(
        "background:#F8FBFF; color:%1; border:1px solid #D0DDE8; border-radius:16px;"
        "font-size:%2px; font-weight:900; padding:8px;"
    ).arg(statusColor).arg(fs->px(24)));
    evalLay->addWidget(scoreBadge, 0);

    QVBoxLayout *evalTextLay = new QVBoxLayout();
    evalTextLay->setSpacing(8);
    QLabel *meta = new QLabel(QStringLiteral("综合得分：%1分    本维度状态：%2    %3").arg(composite).arg(status, advice.weight), evalCard);
    meta->setWordWrap(true);
    meta->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276;").arg(fs->px(16)));
    evalTextLay->addWidget(meta);

    QLabel *analysis = new QLabel(QStringLiteral("具体分析：%1").arg(dimensionAnalysisText(advice, score)), evalCard);
    analysis->setWordWrap(true);
    analysis->setStyleSheet(
        QStringLiteral(
            "background:#F8FBFF; color:#34495E; border:1px solid #E1EAF2; border-radius:12px;"
            "font-size:%1px; line-height:150%; padding:10px;")
            .arg(fs->px(14)));
    evalTextLay->addWidget(analysis);

    QProgressBar *bar = new QProgressBar(evalCard);
    bar->setRange(0, 100);
    bar->setValue(score);
    bar->setFormat(QStringLiteral("%1% (%2)").arg(score).arg(scoreDetail));
    bar->setMinimumHeight(24);
    bar->setStyleSheet(QString(
        "QProgressBar{border:1px solid #D0DDE8; border-radius:11px; background:#EDF3F8; text-align:center; font-weight:bold; color:#34495E;}"
        "QProgressBar::chunk{background:%1; border-radius:11px;}"
    ).arg(statusColor));
    evalTextLay->addWidget(bar);
    evalLay->addLayout(evalTextLay, 1);

    m_dimensionLayout->addWidget(evalCard);
    m_dimensionLayout->addWidget(createDimensionCard(advice, result, m_dimensionContent, true));
    m_dimensionLayout->addStretch(1);
}

QWidget *MedicalAdvicePage::createDimensionOverviewCard(const DimensionAdvice &advice, const ScoreResult &result, int recordStorageIndex, QWidget *parent)
{
    const FontScale *fs = FontScale::instance();
    const int score = dimensionScore(result, advice.key);
    const QString scoreDetail = ScoreEngine::dimensionScoreLabel(result, advice.key);
    const QString status = scoreStatusText(score);
    const QString statusColor = scoreStatusColor(score);

    QFrame *card = new QFrame(parent);
    card->setObjectName("dimensionOverviewCard");
    card->setMinimumHeight(112);
    card->setStyleSheet(
        "QFrame#dimensionOverviewCard{background:#FFFFFF; border:1px solid #D0DDE8; border-radius:16px;}"
        "QLabel{background:transparent; border:none;}"
    );
    QHBoxLayout *lay = new QHBoxLayout(card);
    lay->setContentsMargins(18, 14, 18, 14);
    lay->setSpacing(14);

    QVBoxLayout *textLay = new QVBoxLayout();
    textLay->setSpacing(6);
    QLabel *title = new QLabel(QStringLiteral("%1  ·  %2").arg(advice.name, advice.weight), card);
    title->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276;").arg(fs->px(18)));
    textLay->addWidget(title);

    QLabel *suggestion = new QLabel(dimensionBriefSuggestion(advice, score), card);
    suggestion->setWordWrap(true);
    suggestion->setStyleSheet(
        QStringLiteral("font-size:%1px; color:#34495E; line-height:150%;").arg(fs->px(13)));
    textLay->addWidget(suggestion);
    lay->addLayout(textLay, 1);

    QLabel *scoreLabel = new QLabel(QStringLiteral("%1%\n%2\n%3").arg(score).arg(scoreDetail).arg(status), card);
    scoreLabel->setAlignment(Qt::AlignCenter);
    scoreLabel->setMinimumSize(fs->largeMode() ? 132 : 120, fs->largeMode() ? 74 : 66);
    scoreLabel->setStyleSheet(QString(
        "background:%1; color:#FFFFFF; border-radius:14px; font-size:%2px; font-weight:900; padding:6px;"
    ).arg(statusColor).arg(fs->px(15)));
    lay->addWidget(scoreLabel, 0);

    QPushButton *detailBtn = new QPushButton(QStringLiteral("具体分析"), card);
    detailBtn->setCursor(Qt::PointingHandCursor);
    detailBtn->setMinimumSize(fs->largeMode() ? 126 : 112, fs->largeMode() ? 48 : 42);
    detailBtn->setStyleSheet(
        QStringLiteral(
            "QPushButton{background:#2E86C1; color:#FFFFFF; border:none; border-radius:12px;"
            "font-size:%1px; font-weight:900; padding:6px 14px;}"
            "QPushButton:hover{background:#1A5276;}"
            "QPushButton:pressed{background:#154360;}")
            .arg(fs->px(15)));
    connect(detailBtn, &QPushButton::clicked, this, [this, recordStorageIndex, key = advice.key]() {
        showDimensionDetail(recordStorageIndex, key);
    });
    lay->addWidget(detailBtn, 0);

    return card;
}

QWidget *MedicalAdvicePage::createImageBox(const QString &resourcePath, const QString &caption, QWidget *parent, bool largeMode)
{
    const FontScale *fs = FontScale::instance();
    QFrame *box = new QFrame(parent);
    box->setObjectName("imageBox");
    box->setMinimumWidth(largeMode ? 280 : 150);
    box->setStyleSheet(
        "QFrame#imageBox{background:#FFFFFF; border:1px solid #E1EAF2; border-radius:12px;}"
        "QLabel{border:none; background:transparent;}"
    );
    QVBoxLayout *lay = new QVBoxLayout(box);
    lay->setContentsMargins(largeMode ? 12 : 8, largeMode ? 12 : 8, largeMode ? 12 : 8, largeMode ? 12 : 8);
    lay->setSpacing(8);

    QLabel *img = new QLabel(box);
    img->setAlignment(Qt::AlignCenter);
    const int imageW = largeMode ? 260 : 134;
    const int imageH = largeMode ? 190 : 96;
    img->setMinimumSize(imageW, largeMode ? 170 : 88);
    img->setMaximumHeight(largeMode ? 230 : 112);
    QPixmap pix(resourcePath);
    if (!pix.isNull()) {
        img->setPixmap(pix.scaled(imageW, imageH, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    } else {
        img->setText(QStringLiteral("图片未找到"));
        img->setStyleSheet(
            QStringLiteral("font-size:%1px; color:#A0A0A0;").arg(fs->px(12)));
    }
    lay->addWidget(img);

    QLabel *cap = new QLabel(caption, box);
    cap->setWordWrap(true);
    cap->setAlignment(Qt::AlignCenter);
    cap->setStyleSheet(QString("font-size:%1px; color:#606060; font-weight:%2;")
                       .arg(fs->px(largeMode ? 13 : 12))
                       .arg(largeMode ? 800 : 400));
    lay->addWidget(cap);
    return box;
}

QWidget *MedicalAdvicePage::createDimensionCard(const DimensionAdvice &advice, const ScoreResult &result, QWidget *parent, bool largeImages)
{
    const FontScale *fs = FontScale::instance();
    const int score = dimensionScore(result, advice.key);
    const QString scoreDetail = ScoreEngine::dimensionScoreLabel(result, advice.key);
    const QString status = scoreStatusText(score);
    const QString statusColor = scoreStatusColor(score);

    QFrame *card = new QFrame(parent);
    card->setObjectName("medicalDimensionCard");
    card->setStyleSheet(
        "QFrame#medicalDimensionCard{background:#FFFFFF; border:1px solid #D0DDE8; border-radius:18px;}"
        "QLabel{border:none; background:transparent;}"
    );
    QVBoxLayout *cardLay = new QVBoxLayout(card);
    cardLay->setContentsMargins(18, 16, 18, 16);
    cardLay->setSpacing(12);

    QHBoxLayout *topLay = new QHBoxLayout();
    topLay->setSpacing(12);
    QLabel *name = new QLabel(QStringLiteral("%1  ·  %2").arg(advice.name, advice.weight), card);
    name->setStyleSheet(
        QStringLiteral("font-size:%1px; font-weight:900; color:#1A5276;").arg(fs->px(19)));
    topLay->addWidget(name, 1);

    QLabel *scoreLabel = new QLabel(QStringLiteral("%1% (%2) · %3").arg(score).arg(scoreDetail).arg(status), card);
    scoreLabel->setAlignment(Qt::AlignCenter);
    scoreLabel->setMinimumWidth(fs->largeMode() ? 158 : 142);
    scoreLabel->setStyleSheet(QString(
        "background:%1; color:#FFFFFF; border-radius:12px; font-size:%2px; font-weight:900; padding:7px 12px;"
    ).arg(statusColor).arg(fs->px(15)));
    topLay->addWidget(scoreLabel, 0);
    cardLay->addLayout(topLay);

    QProgressBar *bar = new QProgressBar(card);
    bar->setRange(0, 100);
    bar->setValue(score);
    bar->setFormat(QStringLiteral("%1% (%2)").arg(score).arg(scoreDetail));
    bar->setMinimumHeight(fs->largeMode() ? 28 : 22);
    bar->setStyleSheet(QString(
        "QProgressBar{border:1px solid #D0DDE8; border-radius:10px; background:#EDF3F8; text-align:center; font-weight:bold; color:#34495E;}"
        "QProgressBar::chunk{background:%1; border-radius:10px;}"
    ).arg(statusColor));
    cardLay->addWidget(bar);

    QHBoxLayout *bodyLay = new QHBoxLayout();
    bodyLay->setSpacing(largeImages ? 18 : 14);

    QVBoxLayout *textLay = new QVBoxLayout();
    textLay->setSpacing(8);
    auto makePara = [card, largeImages, fs](const QString &text, const QString &bg, const QString &fg) -> QLabel* {
        QLabel *label = new QLabel(text, card);
        label->setWordWrap(true);
        label->setStyleSheet(QString(
            "background:%1; color:%2; border:1px solid #E1EAF2; border-radius:10px;"
            "font-size:%3px; line-height:150%; padding:9px;"
        ).arg(bg, fg).arg(fs->px(largeImages ? 14 : 13)));
        return label;
    };

    textLay->addWidget(makePara(advice.posture, QStringLiteral("#F8FBFF"), QStringLiteral("#34495E")));
    textLay->addWidget(makePara(advice.possibleReason, QStringLiteral("#F8FBFF"), QStringLiteral("#34495E")));
    textLay->addWidget(makePara(advice.training, QStringLiteral("#F4FFF8"), QStringLiteral("#1E6B3A")));
    textLay->addWidget(makePara(dimensionMedicineText(advice, score), QStringLiteral("#FFF9E8"), QStringLiteral("#6C4F00")));
    bodyLay->addLayout(textLay, largeImages ? 2 : 1);

    QVBoxLayout *imageLay = new QVBoxLayout();
    imageLay->setSpacing(largeImages ? 12 : 10);
    imageLay->addWidget(createImageBox(advice.actionImage, advice.actionCaption, card, largeImages));
    imageLay->addWidget(createImageBox(advice.medicineImage, advice.medicineCaption, card, largeImages));
    imageLay->addStretch(1);
    bodyLay->addLayout(imageLay, largeImages ? 1 : 0);

    cardLay->addLayout(bodyLay);
    return card;
}
