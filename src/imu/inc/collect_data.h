#ifndef COLLECT_DATA_H
#define COLLECT_DATA_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <errno.h>
#include <pthread.h>
#include <time.h>
#include <stdint.h>
#include <math.h>
#include <sys/select.h>
#include <dirent.h>
#include <limits.h>
#include <sys/stat.h>
#include "imu_paths.h"

#define BAUDRATE B115200        // 波特率
#define BUF_SIZE 65536          // 64KB 环形缓冲区
#define FLUSH_THRESHOLD 50      // 每累积50帧, 报告一次进度
#define CSV_DIR_NAME "data"  // CSV文件保存目录名
#define CSV_PATH_MAX (PATH_MAX + 128)        // CSV文件路径最大长度
#define FRAME_LENGTH_ACC_GYRO 20  // 0x55 + 0x61 帧长度 (加速度+角速度+角度)
#define FRAME_LENGTH_ANGLE 10     // 0x55 + 0x53 帧长度 (角度)
#define FRAME_LENGTH_ACC 10       // 0x55 + 0x51 帧长度 (加速度)
#define FRAME_LENGTH_GYRO 10      // 0x55 + 0x52 帧长度 (角速度)
#define FRAME_HEADER1 0x55        // 帧头1
#define FRAME_HEADER2_ACC_GYRO 0x61   // 加速度+角速度+角度帧
#define FRAME_HEADER2_ANGLE 0x53      // 角度帧 (Roll, Pitch, Yaw)
#define FRAME_HEADER2_ACC 0x51        // 加速度帧
#define FRAME_HEADER2_GYRO 0x52       // 角速度帧
#define COLLECTION_TIME_SECONDS 30
#define PREP_TIME_SECONDS 5
#define TARGET_FRAMES (COLLECTION_TIME_SECONDS * 100)    // 目标帧数
#define MAX_RAW_FRAMES 120000   // 最大原始帧数 (20分钟 @ 100Hz)

/* ================================================================
 *  传感器量程 (数据手册固定值)
 *
 *  加速度计: ±16g       → acc(g) = raw / 32768 × 16
 *  陀螺仪:   ±2000°/s   → ω(°/s) = raw / 32768 × 2000
 *  角度:     ±180°      → angle(°) = raw / 32768 × 180
 *
 *  数据格式: 16-bit有符号short, 低字节在前 (Little-Endian)
 *  组合方式: Data = ((short)DataH << 8) | DataL
 *  帧格式:   0x55 0x61 axL axH ayL ayH azL azH
 *            wxL wxH wyL wyH wzL wzH
 *            RollL RollH PitchL PitchH YawL YawH
 *  帧长度:   20字节 (无校验和)
 * ================================================================ */
#define ACC_RANGE   16.0    // 加速度计量程 ±16g (数据手册)
#define GYRO_RANGE  2000.0  // 陀螺仪量程 ±2000°/s (数据手册)
#define ANGLE_RANGE 180.0   // 角度量程 ±180° (数据手册)

/* 环形缓冲区 (串口读取 → 帧解析) */
typedef struct {
    unsigned char buffer[BUF_SIZE];
    int head;
    int tail;
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    int data_available;
} RingBuffer;

/* 原始IMU数据 (int16, 直接从串口帧解析) */
typedef struct {
    int16_t ax;    // X轴加速度 (原始值)
    int16_t ay;    // Y轴加速度 (原始值)
    int16_t az;    // Z轴加速度 (原始值)
    int16_t wx;    // X轴角速度 (原始值)
    int16_t wy;    // Y轴角速度 (原始值)
    int16_t wz;    // Z轴角速度 (原始值)
    int16_t roll;  // X轴角度 (原始值)
    int16_t pitch; // Y轴角度 (原始值)
    int16_t yaw;   // Z轴角度 (原始值)
} IMUData;

/* 物理量IMU数据 (转换后的实际值) */
typedef struct {
    double ax;     // X轴加速度 (m/s²)
    double ay;     // Y轴加速度 (m/s²)
    double az;     // Z轴加速度 (m/s²)
    double wx;     // X轴角速度 (°/s)
    double wy;     // Y轴角速度 (°/s)
    double wz;     // Z轴角速度 (°/s)
    double roll;   // X轴角度 (°)
    double pitch;  // Y轴角度 (°)
    double yaw;    // Z轴角度 (°)
} IMUDataPhysical;

/* 传感器量程信息 */
typedef struct {
    double acc_range;   // 加速度计量程 (±g), 如 2.0, 4.0, 8.0, 16.0
    double gyro_range;  // 陀螺仪量程 (±°/s), 如 125, 250, 500, 1000, 2000
    double acc_bias_x;  // 加速度计X轴零偏 (原始值)
    double acc_bias_y;  // 加速度计Y轴零偏 (原始值)
    double acc_bias_z;  // 加速度计Z轴零偏 (原始值)
    double gyro_bias_wx;// 陀螺仪X轴零偏 (原始值)
    double gyro_bias_wy;// 陀螺仪Y轴零偏 (原始值)
    double gyro_bias_wz;// 陀螺仪Z轴零偏 (原始值)
} SensorRangeInfo;

/* 采集线程上下文 —— 每个IMU一个实例, 完全独立 */
typedef struct {
    const char *port;        /* 串口路径 */
    const char *hand_label;  /* 标识标签, 如 "L" 或 "R" */
    char csv_path[CSV_PATH_MAX]; /* 生成的CSV文件路径 */
    volatile int running;
    int total_frames;
    int target_frames;
    int g_last_flush;
    IMUData *g_raw_data;
    int g_raw_count;
    int g_raw_capacity;
} CollectorCtx;


/**
 * @brief 收集IMU数据, 每次自动生成带时间戳的新CSV文件
 *
 * 流程:
 *   1. 从串口采集原始帧, 存入内存
 *   2. 采集完成后, 自动检测传感器量程
 *   3. 将原始数据转换为物理量 (m/s², °/s, °)
 *   4. 写入CSV文件 (含物理量, 可直接用于分析)
 *
 * @param argc 命令行参数数量
 * @param argv 命令行参数数组
 * @param csv_path_out 输出参数, 用于返回生成的CSV文件路径 (调用者需保证至少CSV_PATH_MAX字节)
 * @return int 0 成功, -1 失败
 */
int collect_data(int argc, char *argv[], char *csv_path_out);

/**
 * @brief 双IMU同步数据采集
 *
 * 同时驱动两个IMU传感器 (左手 + 右手), 各自由独立线程采集,
 * 分别生成带时间戳的CSV文件。
 *
 * @param argc 命令行参数数量
 * @param argv 命令行参数数组
 * @param csv_left  输出: 左手CSV文件路径 (调用者提供CSV_PATH_MAX字节空间)
 * @param csv_right 输出: 右手CSV文件路径
 * @return int 0 成功, -1 失败
 */
int collect_dual_data(int argc, char *argv[], char *csv_left, char *csv_right);

#endif
