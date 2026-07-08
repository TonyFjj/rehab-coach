#include "scoreengine.h"
#include <QRandomGenerator>
#include <QStringList>
#include <QJsonArray>
#include <QJsonObject>
#include <QtGlobal>

ScoreEngine::ScoreEngine(QObject *parent) : QObject(parent)
{
    m_weights = {
        {"range_of_motion", 0.30}, {"smoothness", 0.25},
        {"tremor", 0.20}, {"symmetry", 0.15},
        {"speed", 0.05}, {"fatigue", 0.05}
    };
}

int ScoreEngine::scoreToLevel(int s)
{
    if (s < 40) {
        return 1;
    }
    if (s <= 60) {
        return 2;
    }
    if (s <= 80) {
        return 3;
    }
    return 4;
}

QString ScoreEngine::levelName(int l) {
    static QMap<int,QString> n={{1,"L1 保护辅助"},{2,"L2 基础恢复"},{3,"L3 稳定提升"},{4,"L4 巩固痊愈"}};
    return n.value(l,"未评估");
}

QString ScoreEngine::levelColor(int l) {
    static QMap<int,QString> c={{1,"#E74C3C"},{2,"#F39C12"},{3,"#2E86C1"},{4,"#27AE60"}};
    return c.value(l,"#A0A0A0");
}

QString ScoreEngine::randomAdviceForScore(int score)
{
    static const QStringList excellentAdvices = {
        QStringLiteral("当前恢复表现优秀，继续按康复师计划维持训练频率，不要突然加大负荷。"),
        QStringLiteral("训练前先做肩、肘、腕轻柔活动，让关节充分热身后再进入正式动作。"),
        QStringLiteral("保持动作慢起慢落，追求稳定和控制，比单纯追求次数更重要。"),
        QStringLiteral("可以在无疼痛前提下逐步增加日常使用患侧手臂的机会，如轻拿水杯或整理衣物。"),
        QStringLiteral("继续记录每次训练后的酸胀感和疲劳程度，便于医生或康复师调整方案。"),
        QStringLiteral("恢复较好时也要避免突然搬重物、快速挥臂或长时间举高手臂。"),
        QStringLiteral("每天保持规律睡眠和足够蛋白质摄入，有助于肌肉力量和组织修复。"),
        QStringLiteral("训练后若出现明显疼痛、肿胀或麻木，应暂停并咨询专业人员。"),
        QStringLiteral("可将训练重点从单一幅度逐步转向协调性、耐力和精细控制。"),
        QStringLiteral("保持肩胛和躯干稳定，避免用耸肩或身体后仰代偿手臂动作。"),
        QStringLiteral("建议继续进行全范围关节活动训练，防止恢复后期再次僵硬。"),
        QStringLiteral("日常工作学习中注意每30到40分钟活动肩颈和手臂，减少久坐僵硬。"),
        QStringLiteral("如果动作质量稳定，可在专业指导下加入轻阻力弹力带训练。"),
        QStringLiteral("训练时保持自然呼吸，不要憋气用力，以免增加身体负担。"),
        QStringLiteral("继续保持左右手臂对称练习，避免健侧过度代偿。"),
        QStringLiteral("恢复较好并不代表完全痊愈，仍应遵循循序渐进原则。"),
        QStringLiteral("洗澡、穿衣、梳头等生活动作可以作为温和的功能训练，但不要勉强到疼痛。"),
        QStringLiteral("训练结束后做轻柔拉伸和放松，帮助减轻肌肉紧张。"),
        QStringLiteral("保持积极心态，稳定训练比短期高强度冲刺更利于长期恢复。"),
        QStringLiteral("如医生允许，可结合散步等低强度有氧活动改善全身循环。"),
        QStringLiteral("维持正确坐姿和站姿，减少圆肩、含胸对肩关节活动的影响。"),
        QStringLiteral("可把目标设为动作更平稳、更对称，而不是盲目追求更高分。"),
        QStringLiteral("继续按时复诊或复评，确认是否可以进入更高阶训练。"),
        QStringLiteral("日常可使用患侧完成轻量、安全的任务，逐步恢复生活自信。"),
        QStringLiteral("若连续多次得分稳定在高水平，可与康复师讨论减少监督频率或调整训练阶段。")
    };

    static const QStringList goodAdvices = {
        QStringLiteral("当前恢复情况较好，建议继续坚持训练，并优先提升动作稳定性。"),
        QStringLiteral("训练时控制速度，避免为了完成次数而出现甩臂或借力动作。"),
        QStringLiteral("每次训练前后观察疼痛变化，轻微酸胀可记录，明显疼痛应暂停。"),
        QStringLiteral("可以把动作分成小幅度、多组次完成，逐步扩大活动范围。"),
        QStringLiteral("注意肩部放松，避免耸肩代偿造成颈肩部疲劳。"),
        QStringLiteral("建议在安全范围内增加手臂日常功能使用，如轻柔擦桌、拿取轻物。"),
        QStringLiteral("保持训练规律，每天少量多次通常比偶尔大量训练更稳妥。"),
        QStringLiteral("若动作末端控制不稳，可在末端停留1到2秒后再缓慢放下。"),
        QStringLiteral("训练中应保持身体正对前方，减少躯干旋转代偿。"),
        QStringLiteral("可用镜子观察左右动作是否一致，及时修正偏斜和耸肩。"),
        QStringLiteral("如果疲劳后动作明显变形，应减少当次训练量而不是硬撑完成。"),
        QStringLiteral("睡前避免长时间压迫患侧手臂，保持舒适支撑。"),
        QStringLiteral("日常拿取物品时尽量靠近身体，减少远距离伸手带来的负担。"),
        QStringLiteral("如已获得医生许可，可尝试低阻力、慢速度的力量控制训练。"),
        QStringLiteral("训练时关注动作质量、疼痛等级和第二天反应，三者都稳定再考虑进阶。"),
        QStringLiteral("保持充足饮水和均衡饮食，有助于体力恢复和训练耐受。"),
        QStringLiteral("若出现刺痛、麻木、明显无力或肿胀，应停止训练并联系医生。"),
        QStringLiteral("建议把高难度动作安排在精神状态较好、身体不疲劳的时候完成。"),
        QStringLiteral("可以把患侧手臂参与到穿衣、洗漱等轻度活动中，但不要强行拉伸。"),
        QStringLiteral("训练后可进行轻柔放松，避免立刻进行搬运或重复劳动。"),
        QStringLiteral("继续保持良好姿势，肩胛稳定有助于提升手臂抬举质量。"),
        QStringLiteral("分数处于提升阶段，重点是稳定重复正确动作，减少波动。"),
        QStringLiteral("若连续几次得分上升，可与康复师确认是否增加动作难度。"),
        QStringLiteral("如果分数忽高忽低，建议优先检查睡眠、疼痛和训练前热身是否稳定。"),
        QStringLiteral("保持耐心，良好恢复通常来自持续的小幅进步。")
    };

    static const QStringList basicAdvices = {
        QStringLiteral("当前恢复仍需加强，建议降低动作难度，先保证无痛范围内的正确动作。"),
        QStringLiteral("训练时不要追求高幅度，先从舒适范围开始，逐步增加活动角度。"),
        QStringLiteral("建议在家属或康复人员看护下完成较困难动作，避免跌倒或拉伤。"),
        QStringLiteral("若抬手困难，可先进行桌面滑动、钟摆样摆动等低负荷活动。"),
        QStringLiteral("训练过程中如疼痛达到明显不适，应立即减小幅度或停止。"),
        QStringLiteral("每天可分多次进行短时间练习，避免一次训练过久导致疲劳。"),
        QStringLiteral("优先练习肩、肘、腕的基础活动度，再逐步加入力量训练。"),
        QStringLiteral("注意患侧手臂保暖，避免寒冷环境下肌肉紧张加重僵硬。"),
        QStringLiteral("动作时保持呼吸平稳，避免屏气和突然用力。"),
        QStringLiteral("如果出现手指肿胀，可在医生指导下进行握拳伸指等轻柔活动。"),
        QStringLiteral("训练前检查座椅和地面是否稳定，确保康复环境安全。"),
        QStringLiteral("建议记录哪类动作最困难，下次复诊时反馈给医生或康复师。"),
        QStringLiteral("可以先用健侧辅助患侧完成动作，但不要强行拉到疼痛位置。"),
        QStringLiteral("日常生活中减少搬重物、提拉重袋和长时间悬空持物。"),
        QStringLiteral("若训练后第二天疼痛明显增加，说明强度可能偏高，需要下调。"),
        QStringLiteral("保持规律作息，疲劳和睡眠不足会影响动作控制和恢复速度。"),
        QStringLiteral("可把训练目标设为动作更顺畅，而不是立刻达到完整角度。"),
        QStringLiteral("建议在康复师指导下确认是否存在代偿动作，如耸肩、侧身或甩臂。"),
        QStringLiteral("训练中可使用枕头或毛巾支撑手臂，降低肩部负担。"),
        QStringLiteral("如果关节明显发热、红肿或持续疼痛，应暂停训练并就医。"),
        QStringLiteral("恢复中期容易急于进阶，建议先把基础动作做稳再增加难度。"),
        QStringLiteral("日常可以多做轻柔开合手、转腕和屈伸肘动作，帮助维持灵活性。"),
        QStringLiteral("训练空间应保持明亮、无杂物，减少因动作不稳导致的意外。"),
        QStringLiteral("如果得分长期停留在该区间，建议复查康复计划是否需要调整。"),
        QStringLiteral("请把每次训练后的疼痛、疲劳和活动范围变化记录下来，方便持续追踪。")
    };

    static const QStringList protectAdvices = {
        QStringLiteral("当前得分偏低，建议先暂停高强度训练，在医生或康复治疗师指导下制定计划。"),
        QStringLiteral("请以安全和无痛为第一目标，不要强行抬高手臂或拉伸到疼痛位置。"),
        QStringLiteral("若伴随明显肿胀、麻木、刺痛或力量突然下降，应尽快就医评估。"),
        QStringLiteral("训练可从被动或辅助活动开始，由家属或治疗师帮助控制幅度。"),
        QStringLiteral("建议每次练习时间短一些，重点观察身体反应，而不是追求次数。"),
        QStringLiteral("目前不建议搬重物、快速挥臂、撑地起身或进行对抗性训练。"),
        QStringLiteral("保持患侧手臂舒适支撑，休息时避免长时间悬空或受压。"),
        QStringLiteral("若医生允许，可进行手指开合、腕部轻动等低负荷活动维持循环。"),
        QStringLiteral("出现疼痛加重时不要忍痛训练，应及时停止并记录诱发动作。"),
        QStringLiteral("建议优先改善基础活动度，再逐步进入主动控制和力量训练。"),
        QStringLiteral("康复环境要防滑、无障碍，必要时请家属在旁协助。"),
        QStringLiteral("保持良好睡眠和营养，身体状态差时应减少训练量。"),
        QStringLiteral("如果近期做过手术、骨折或脱位处理，必须严格遵循医生限制。"),
        QStringLiteral("请避免自行使用大重量器械或弹力带，以免造成二次损伤。"),
        QStringLiteral("可以把目标定为轻柔活动、减轻僵硬和建立训练习惯。"),
        QStringLiteral("若无法完成当前动作，请改为更低级别动作，不要勉强完成测评动作。"),
        QStringLiteral("建议复诊时带上测评分数和困难动作记录，帮助医生判断恢复阶段。"),
        QStringLiteral("训练前确认疼痛水平，如果静息时已明显疼痛，当天应以休息和咨询为主。"),
        QStringLiteral("患侧手臂日常活动以轻量、安全为主，避免突然抓取或提拉。"),
        QStringLiteral("如感觉肩关节不稳、像要滑出，应停止训练并尽快咨询骨科或康复科。"),
        QStringLiteral("请优先练习正确姿势和基础控制，不要用身体摆动带动手臂。"),
        QStringLiteral("如果分数连续偏低，建议重新评估动作选择、传感器佩戴和康复方案。"),
        QStringLiteral("保持积极但谨慎的恢复节奏，小幅、无痛、可重复的动作最适合当前阶段。"),
        QStringLiteral("可在医生指导下使用支具、毛巾或桌面支撑来降低训练难度。"),
        QStringLiteral("当前阶段需要更多保护和专业指导，等疼痛和控制能力改善后再逐步进阶。")
    };

    const QStringList *pool = &protectAdvices;
    if (score > 80) {
        pool = &excellentAdvices;
    } else if (score > 60) {
        pool = &goodAdvices;
    } else if (score >= 40) {
        pool = &basicAdvices;
    }

    if (!pool || pool->isEmpty()) {
        return QStringLiteral("请根据医生或康复治疗师建议，循序渐进完成训练。");
    }
    const int index = QRandomGenerator::global()->bounded(pool->size());
    return pool->at(index);
}

ScoreResult ScoreEngine::calculate(const QMap<QString,double> &raw)
{
    ScoreResult r; r.timestamp = QDateTime::currentDateTime();
    auto norm = [](double v,double lo,double hi)->double{ return qBound(0.0,1.0-(v-lo)/(hi-lo),1.0); };
    r.dims["range_of_motion"] = qBound(0.0, raw.value("range_of_motion",0)/180.0, 1.0);
    r.dims["smoothness"]      = norm(raw.value("smoothness",2.0), 0, 2);
    r.dims["tremor"]          = norm(raw.value("tremor",0.6), 0, 0.6);
    r.dims["symmetry"]        = norm(raw.value("symmetry",60), 0, 60);
    r.dims["speed"]           = norm(raw.value("speed",15), 1, 15);
    r.dims["fatigue"]         = norm(raw.value("fatigue",0.5), 0, 0.5);
    double w=0;
    for (auto it=m_weights.begin(); it!=m_weights.end(); ++it)
        w += r.dims.value(it.key(),0) * it.value();
    r.compositeScore = qRound(w*100);
    r.level = scoreToLevel(r.compositeScore);
    r.levelName = levelName(r.level);
    r.levelColor = levelColor(r.level);
    r.advice = randomAdviceForScore(r.compositeScore);
    return r;
}

void ScoreEngine::onImuData(const QMap<QString,double> &raw) { emit scoreReady(calculate(raw)); }

ScoreResult ScoreEngine::fromEnginePayload(const QJsonObject &payload)
{
    ScoreResult result;
    result.timestamp = QDateTime::currentDateTime();
    result.compositeScore = qRound(payload.value(QStringLiteral("total_score")).toDouble(0));
    result.source = payload.value(QStringLiteral("source")).toString();

    const QString levelCode = payload.value(QStringLiteral("level")).toString();
    if (levelCode.startsWith(QStringLiteral("L"), Qt::CaseInsensitive)) {
        bool ok = false;
        const int n = levelCode.mid(1).toInt(&ok);
        if (ok) {
            result.level = n;
        }
    }
    if (result.level <= 0) {
        result.level = scoreToLevel(result.compositeScore);
    }

    result.levelName = payload.value(QStringLiteral("level_name")).toString();
    if (result.levelName.isEmpty()) {
        result.levelName = levelName(result.level);
    }
    result.levelColor = levelColor(result.level);

    static const QMap<QString, QString> dimMap = {
        {QStringLiteral("range_of_motion"), QStringLiteral("抬举幅度")},
        {QStringLiteral("smoothness"), QStringLiteral("运动平滑度")},
        {QStringLiteral("tremor"), QStringLiteral("震颤程度")},
        {QStringLiteral("symmetry"), QStringLiteral("双侧对称性")},
        {QStringLiteral("speed"), QStringLiteral("运动速度")},
        {QStringLiteral("endurance"), QStringLiteral("运动耐力")},
        {QStringLiteral("fatigue"), QStringLiteral("运动耐力")},
    };

    static const QMap<QString, double> dimMaxPoints = {
        {QStringLiteral("range_of_motion"), 30.0},
        {QStringLiteral("smoothness"), 25.0},
        {QStringLiteral("tremor"), 20.0},
        {QStringLiteral("symmetry"), 15.0},
        {QStringLiteral("speed"), 5.0},
        {QStringLiteral("endurance"), 5.0},
        {QStringLiteral("fatigue"), 5.0},
    };

    auto normalizeDim = [&](const QString &enKey, double v) -> double {
        const double maxPts = dimMaxPoints.value(enKey, 0.0);
        if (maxPts > 0.0) {
            if (v > 1.0) {
                return qBound(0.0, v / maxPts, 1.0);
            }
            const double implied = v * 100.0;
            if (implied >= 1.0 && implied <= maxPts + 0.01
                && qAbs(implied - qRound(implied)) < 0.05) {
                return qBound(0.0, implied / maxPts, 1.0);
            }
            return qBound(0.0, v, 1.0);
        }
        return v > 1.0 ? qBound(0.0, v / 100.0, 1.0) : qBound(0.0, v, 1.0);
    };

    const QJsonObject dims = payload.value(QStringLiteral("dimension_scores")).toObject();
    for (auto it = dims.begin(); it != dims.end(); ++it) {
        const QString key = it.key();
        const double v = it.value().toDouble();
        if (key.startsWith(QStringLiteral("block_"))) {
            result.dims[key] = v > 1.0 ? v / 100.0 : v;
            continue;
        }
        const QString mapped = dimMap.value(key, key);
        QString enKey = key;
        if (!dimMaxPoints.contains(enKey)) {
            for (auto dm = dimMap.constBegin(); dm != dimMap.constEnd(); ++dm) {
                if (dm.value() == key) {
                    enKey = dm.key();
                    break;
                }
            }
        }
        result.dims[mapped] = normalizeDim(enKey, v);
    }

    const QJsonArray names = payload.value(QStringLiteral("action_names")).toArray();
    for (const QJsonValue &value : names) {
        const QString name = value.toString().trimmed();
        if (!name.isEmpty()) {
            result.blockNames.append(name);
        }
    }

    const QJsonArray scores = payload.value(QStringLiteral("action_scores")).toArray();
    for (const QJsonValue &value : scores) {
        result.blockScores.append(qBound(0, qRound(value.toDouble()), 100));
    }

    if (result.blockScores.isEmpty() && !result.blockNames.isEmpty()) {
        for (int i = 0; i < result.blockNames.size(); ++i) {
            const QString key = QStringLiteral("block_%1").arg(i + 1);
            if (result.dims.contains(key)) {
                result.blockScores.append(qRound(result.dims.value(key) * 100.0));
            }
        }
    }

    result.advice = payload.value(QStringLiteral("advice")).toString();
    if (result.advice.isEmpty()) {
        result.advice = randomAdviceForScore(result.compositeScore);
    }
    return result;
}

namespace {

const QMap<QString, QString> &dimensionCnMap()
{
    static const QMap<QString, QString> map = {
        {QStringLiteral("range_of_motion"), QStringLiteral("抬举幅度")},
        {QStringLiteral("smoothness"), QStringLiteral("运动平滑度")},
        {QStringLiteral("tremor"), QStringLiteral("震颤程度")},
        {QStringLiteral("symmetry"), QStringLiteral("双侧对称性")},
        {QStringLiteral("speed"), QStringLiteral("运动速度")},
        {QStringLiteral("endurance"), QStringLiteral("运动耐力")},
        {QStringLiteral("fatigue"), QStringLiteral("运动耐力")},
    };
    return map;
}

const QMap<QString, double> &dimensionMaxMap()
{
    static const QMap<QString, double> map = {
        {QStringLiteral("range_of_motion"), 30.0},
        {QStringLiteral("smoothness"), 25.0},
        {QStringLiteral("tremor"), 20.0},
        {QStringLiteral("symmetry"), 15.0},
        {QStringLiteral("speed"), 5.0},
        {QStringLiteral("endurance"), 5.0},
        {QStringLiteral("fatigue"), 5.0},
    };
    return map;
}

const QStringList &coreDimensionKeys()
{
    static const QStringList keys = {
        QStringLiteral("range_of_motion"),
        QStringLiteral("smoothness"),
        QStringLiteral("tremor"),
        QStringLiteral("symmetry"),
        QStringLiteral("speed"),
        QStringLiteral("fatigue"),
    };
    return keys;
}

double ratioFromRawValue(const QString &englishKey, double v)
{
    const double maxPts = dimensionMaxMap().value(englishKey, 0.0);
    if (maxPts <= 0.0) {
        if (v > 1.0) {
            return qBound(0.0, v / 100.0, 1.0);
        }
        return qBound(0.0, v, 1.0);
    }

    if (v > 1.0) {
        return qBound(0.0, v / maxPts, 1.0);
    }

    const double impliedPoints = v * 100.0;
    if (impliedPoints >= 1.0 && impliedPoints <= maxPts + 0.01
        && qAbs(impliedPoints - qRound(impliedPoints)) < 0.05) {
        return qBound(0.0, impliedPoints / maxPts, 1.0);
    }
    return qBound(0.0, v, 1.0);
}

} // namespace

QString ScoreEngine::resolveEnglishDimensionKey(const QString &key)
{
    if (dimensionMaxMap().contains(key)) {
        return key;
    }
    for (auto it = dimensionCnMap().constBegin(); it != dimensionCnMap().constEnd(); ++it) {
        if (it.value() == key) {
            return it.key() == QStringLiteral("endurance")
                    ? QStringLiteral("fatigue")
                    : it.key();
        }
    }
    return key;
}

QString ScoreEngine::dimensionCnName(const QString &englishKey)
{
    const QString resolved = resolveEnglishDimensionKey(englishKey);
    if (resolved == QStringLiteral("fatigue")) {
        return QStringLiteral("运动耐力");
    }
    return dimensionCnMap().value(resolved);
}

double ScoreEngine::dimensionMaxPoints(const QString &englishKey)
{
    return dimensionMaxMap().value(resolveEnglishDimensionKey(englishKey), 0.0);
}

double ScoreEngine::dimensionRawValue(const ScoreResult &result, const QString &englishKey)
{
    const QString resolved = resolveEnglishDimensionKey(englishKey);
    const QString cn = dimensionCnName(resolved);
    if (result.dims.contains(resolved)) {
        return result.dims.value(resolved);
    }
    if (result.dims.contains(cn)) {
        return result.dims.value(cn);
    }
    if (resolved == QStringLiteral("fatigue") && result.dims.contains(QStringLiteral("endurance"))) {
        return result.dims.value(QStringLiteral("endurance"));
    }
    return 0.0;
}

double ScoreEngine::dimensionDisplayRatio(const ScoreResult &result, const QString &englishOrCnKey)
{
    const QString englishKey = resolveEnglishDimensionKey(englishOrCnKey);
    return ratioFromRawValue(englishKey, dimensionRawValue(result, englishKey));
}

int ScoreEngine::dimensionDisplayPercent(const ScoreResult &result, const QString &englishOrCnKey)
{
    return qBound(0, qRound(dimensionDisplayRatio(result, englishOrCnKey) * 100.0), 100);
}

QPair<int, int> ScoreEngine::dimensionDisplayPoints(const ScoreResult &result, const QString &englishOrCnKey)
{
    const QString englishKey = resolveEnglishDimensionKey(englishOrCnKey);
    const double ratio = dimensionDisplayRatio(result, englishOrCnKey);
    const double maxPts = dimensionMaxPoints(englishKey);
    if (maxPts <= 0.0) {
        return {qRound(ratio * 100.0), 100};
    }
    return {qRound(ratio * maxPts), qRound(maxPts)};
}

QString ScoreEngine::dimensionScoreLabel(const ScoreResult &result, const QString &englishOrCnKey)
{
    const int pct = dimensionDisplayPercent(result, englishOrCnKey);
    const QPair<int, int> pts = dimensionDisplayPoints(result, englishOrCnKey);
    if (pts.second > 0 && pts.second != 100) {
        return QStringLiteral("%1/%2 (%3%)").arg(pts.first).arg(pts.second).arg(pct);
    }
    return QStringLiteral("%1%").arg(pct);
}

bool ScoreEngine::assessmentDimensionsEqual(const ScoreResult &a, const ScoreResult &b)
{
    for (const QString &key : coreDimensionKeys()) {
        const double ra = dimensionDisplayRatio(a, key);
        const double rb = dimensionDisplayRatio(b, key);
        if (qAbs(ra - rb) > 0.005) {
            return false;
        }
    }
    return true;
}
