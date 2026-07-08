#include "actiondb.h"

ActionDB::ActionDB(QObject *parent) : QObject(parent) { initActions(); }

void ActionDB::initActions()
{
    // L1 卧床被动 (0-30分)
    m_actions.append({1,1,"仰卧肩关节被动外旋","肩关节外旋",1,"仰卧位，辅助肩关节外旋0-40度","#E74C3C"});
    m_actions.append({2,1,"仰卧肘关节屈伸","肘关节屈伸",1,"仰卧位，肘关节缓慢屈曲伸展0-150度","#E74C3C"});
    m_actions.append({3,1,"仰卧踝泵运动","踝关节背伸跖屈",1,"仰卧位，踝关节缓慢背伸跖屈交替","#E74C3C"});
    m_actions.append({4,1,"仰卧深呼吸训练","胸廓扩张",1,"仰卧位，腹式深呼吸配合上肢上举","#E74C3C"});

    // L2 坐姿辅助 (31-60分)
    m_actions.append({5,2,"坐姿肩关节前屈上举","肩关节前屈",2,"坐姿，双手前屈上举至120度保持3秒","#F39C12"});
    m_actions.append({6,2,"坐姿肩关节外展","肩关节外展",2,"坐姿，双手侧平举至90度保持3秒","#F39C12"});
    m_actions.append({7,2,"坐姿膝关节伸展","膝关节伸展",2,"坐姿，单腿缓慢伸直保持3秒交替","#F39C12"});
    m_actions.append({8,2,"坐姿上肢协调性训练","双侧协调",3,"坐姿，双手交替前推后拉划船动作","#F39C12"});

    // L3 站立主动 (61-80分)
    m_actions.append({9,3,"站立肩关节全幅前屈","肩关节前屈",3,"站立，双手从体前举过头顶全范围","#2E86C1"});
    m_actions.append({10,3,"站立半蹲训练","膝关节屈伸",4,"站立，双手前平举缓慢半蹲至90度","#2E86C1"});
    m_actions.append({11,3,"站立重心转移","平衡能力",3,"站立，重心左右前后缓慢转移","#2E86C1"});
    m_actions.append({12,3,"站立单脚平衡","平衡能力",4,"站立，单脚抬起保持10秒换脚","#2E86C1"});

    // L4 全幅主动 (81-100分)
    m_actions.append({13,4,"太极拳式复合运动","全身协调",4,"站立，太极拳起势到收势全套动作","#27AE60"});
    m_actions.append({14,4,"站立上肢负重训练","肩关节力量",4,"站立，持轻量哑铃侧平举上举交替","#27AE60"});
    m_actions.append({15,4,"站立单脚平衡进阶","动态平衡",5,"站立，交替单脚抬起保持平衡","#27AE60"});
    m_actions.append({16,4,"站立身体旋转协调","躯干旋转",4,"站立，双手平举身体左右旋转90度","#27AE60"});
}

QList<ActionInfo> ActionDB::actionsByLevel(int level) const
{
    QList<ActionInfo> result;
    for (const auto &a : m_actions)
        if (a.level == level) result.append(a);
    return result;
}

ActionInfo ActionDB::action(int id) const
{
    for (const auto &a : m_actions)
        if (a.id == id) return a;
    return ActionInfo();
}
