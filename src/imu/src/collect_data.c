#include "collect_data.h"

#define SERIAL_DEVICE_MAX 16
#define SERIAL_PATH_MAX PATH_MAX

static void generate_csv_path(const char *label, char *path_out)
{
    time_t now = time(NULL);
    struct tm *t = localtime(&now);

    imu_ensure_data_dir();
    snprintf(path_out, CSV_PATH_MAX,
             "%s/IMU_data_%s_%04d%02d%02d_%02d%02d%02d.csv",
             imu_get_data_dir(), label,
             t->tm_year + 1900, t->tm_mon + 1, t->tm_mday,
             t->tm_hour, t->tm_min, t->tm_sec);
}

static int serial_name_match(const char *name)
{
    return strncmp(name, "ttyACM", 6) == 0 || strncmp(name, "ttyUSB", 6) == 0;
}

static int compare_serial_path(const void *a, const void *b)
{
    const char *pa = (const char *)a;
    const char *pb = (const char *)b;
    return strcmp(pa, pb);
}

static int find_serial_ports(char ports[][SERIAL_PATH_MAX], int max_ports)
{
    DIR *dir = opendir("/dev");
    struct dirent *entry;
    int count = 0;

    if (!dir) {
        perror("Failed to scan /dev");
        return 0;
    }

    while ((entry = readdir(dir)) != NULL && count < max_ports) {
        if (!serial_name_match(entry->d_name)) continue;

        snprintf(ports[count], SERIAL_PATH_MAX, "/dev/%s", entry->d_name);
        if (access(ports[count], R_OK) == 0) {
            count++;
        }
    }
    closedir(dir);

    qsort(ports, count, SERIAL_PATH_MAX, compare_serial_path);
    return count;
}

static int choose_serial_ports(char *left_port, char *right_port)
{
    const char *env_left = getenv("IMU_LEFT");
    const char *env_right = getenv("IMU_RIGHT");
    if (env_left && env_left[0] && env_right && env_right[0]) {
        snprintf(left_port, SERIAL_PATH_MAX, "%s", env_left);
        snprintf(right_port, SERIAL_PATH_MAX, "%s", env_right);
        printf("[serial] 环境变量 IMU_LEFT=%s IMU_RIGHT=%s\n", left_port, right_port);
        return 0;
    }

    char ports[SERIAL_DEVICE_MAX][SERIAL_PATH_MAX];
    int count = find_serial_ports(ports, SERIAL_DEVICE_MAX);

    if (count < 2) {
        fprintf(stderr, "[serial] Need 2 IMU serial devices, found %d. Checked /dev/ttyACM* and /dev/ttyUSB*.\n", count);
        return -1;
    }

    snprintf(left_port, SERIAL_PATH_MAX, "%s", ports[0]);
    snprintf(right_port, SERIAL_PATH_MAX, "%s", ports[1]);
    printf("[serial] Auto selected left=%s right=%s\n", left_port, right_port);
    return 0;
}

static int choose_single_serial_port(char *port)
{
    char ports[SERIAL_DEVICE_MAX][SERIAL_PATH_MAX];
    int count = find_serial_ports(ports, SERIAL_DEVICE_MAX);

    if (count < 1) {
        fprintf(stderr, "[serial] Need 1 IMU serial device, found 0. Checked /dev/ttyACM* and /dev/ttyUSB*.\n");
        return -1;
    }

    snprintf(port, SERIAL_PATH_MAX, "%s", ports[0]);
    printf("[serial] Auto selected port=%s\n", port);
    return 0;
}

/* ================================================================
 *  辅助函数: 将原始帧存入ctx的动态数组
 * ================================================================ */
static int store_raw_frame(CollectorCtx *ctx, const IMUData *frame)
{
    if (ctx->g_raw_count >= ctx->g_raw_capacity) {
        int new_cap = ctx->g_raw_capacity == 0 ? 4096 : ctx->g_raw_capacity * 2;
        if (new_cap > MAX_RAW_FRAMES) new_cap = MAX_RAW_FRAMES;
        IMUData *new_buf = (IMUData *)realloc(ctx->g_raw_data, new_cap * sizeof(IMUData));
        if (!new_buf) {
            fprintf(stderr, "[%s 警告] 内存不足, 无法存储更多帧 (已存 %d 帧)\n",
                    ctx->hand_label, ctx->g_raw_count);
            return -1;
        }
        ctx->g_raw_data = new_buf;
        ctx->g_raw_capacity = new_cap;
    }
    ctx->g_raw_data[ctx->g_raw_count] = *frame;
    ctx->g_raw_count++;
    return 0;
}

/* ================================================================
 *  量程检测: 寻找稳定窗口 + 陀螺仪零偏
 * ================================================================ */
static void find_stable_window(CollectorCtx *ctx, int *ref_start, int *ref_count)
{
    *ref_start = PREP_TIME_SECONDS * 100;
    *ref_count = 100;
    int found = 0;

    for (int start = PREP_TIME_SECONDS * 100 - 100;
         start <= PREP_TIME_SECONDS * 100 && start + 100 <= ctx->g_raw_count;
         start += 10) {
        if (start < 0) continue;
        double sum = 0, sum2 = 0;
        for (int j = start; j < start + 100 && j < ctx->g_raw_count; j++) {
            double amag = sqrt((double)ctx->g_raw_data[j].ax * ctx->g_raw_data[j].ax +
                               (double)ctx->g_raw_data[j].ay * ctx->g_raw_data[j].ay +
                               (double)ctx->g_raw_data[j].az * ctx->g_raw_data[j].az);
            sum += amag; sum2 += amag * amag;
        }
        double mean = sum / 100;
        double var = sum2 / 100 - mean * mean;
        double std = (var > 0) ? sqrt(var) : 0;
        if (mean > 500 && std < mean * 0.2) {
            *ref_start = start; *ref_count = 100; found = 1; break;
        }
    }

    if (!found) {
        for (int start = 0; start + 100 <= ctx->g_raw_count && start < PREP_TIME_SECONDS * 100; start += 10) {
            double sum = 0, sum2 = 0;
            for (int j = start; j < start + 100 && j < ctx->g_raw_count; j++) {
                double amag = sqrt((double)ctx->g_raw_data[j].ax * ctx->g_raw_data[j].ax +
                                   (double)ctx->g_raw_data[j].ay * ctx->g_raw_data[j].ay +
                                   (double)ctx->g_raw_data[j].az * ctx->g_raw_data[j].az);
                sum += amag; sum2 += amag * amag;
            }
            double mean = sum / 100;
            double var = sum2 / 100 - mean * mean;
            double std = (var > 0) ? sqrt(var) : 0;
            if (mean > 500 && std < mean * 0.2) {
                *ref_start = start; *ref_count = 100; found = 1; break;
            }
        }
    }

    if (!found) {
        for (int start = PREP_TIME_SECONDS * 100 + 1; start + 100 <= ctx->g_raw_count; start += 10) {
            double sum = 0, sum2 = 0;
            for (int j = start; j < start + 100 && j < ctx->g_raw_count; j++) {
                double amag = sqrt((double)ctx->g_raw_data[j].ax * ctx->g_raw_data[j].ax +
                                   (double)ctx->g_raw_data[j].ay * ctx->g_raw_data[j].ay +
                                   (double)ctx->g_raw_data[j].az * ctx->g_raw_data[j].az);
                sum += amag; sum2 += amag * amag;
            }
            double mean = sum / 100;
            double var = sum2 / 100 - mean * mean;
            double std = (var > 0) ? sqrt(var) : 0;
            if (mean > 500 && std < mean * 0.2) {
                *ref_start = start; *ref_count = 100; found = 1; break;
            }
        }
    }

    if (!found) {
        *ref_start = (ctx->g_raw_count > PREP_TIME_SECONDS * 100) ? PREP_TIME_SECONDS * 100 : 0;
        *ref_count = 100;
        if (*ref_start + *ref_count > ctx->g_raw_count)
            *ref_count = ctx->g_raw_count - *ref_start;
    }
}

static void detect_sensor_ranges(CollectorCtx *ctx, SensorRangeInfo *info)
{
    memset(info, 0, sizeof(SensorRangeInfo));
    info->acc_range = ACC_RANGE;
    info->gyro_range = GYRO_RANGE;

    if (ctx->g_raw_count < 100) return;

    int ref_start, ref_count;
    find_stable_window(ctx, &ref_start, &ref_count);

    double sum_wx = 0, sum_wy = 0, sum_wz = 0;
    for (int i = ref_start; i < ref_start + ref_count && i < ctx->g_raw_count; i++) {
        sum_wx += ctx->g_raw_data[i].wx;
        sum_wy += ctx->g_raw_data[i].wy;
        sum_wz += ctx->g_raw_data[i].wz;
    }
    info->gyro_bias_wx = sum_wx / ref_count;
    info->gyro_bias_wy = sum_wy / ref_count;
    info->gyro_bias_wz = sum_wz / ref_count;

    printf("[%s 量程] 加速度计: ±%.0fg, 陀螺仪: ±%.0f°/s, 角度: ±%.0f° (数据手册)\n",
           ctx->hand_label,
           info->acc_range, info->gyro_range, ANGLE_RANGE);
    printf("[%s 零偏] 陀螺仪(raw): wx=%.1f wy=%.1f wz=%.1f\n",
           ctx->hand_label,
           info->gyro_bias_wx, info->gyro_bias_wy, info->gyro_bias_wz);
    printf("[%s 零偏] 陀螺仪(°/s): wx=%.1f wy=%.1f wz=%.1f\n",
           ctx->hand_label,
           info->gyro_bias_wx / 32768.0 * GYRO_RANGE,
           info->gyro_bias_wy / 32768.0 * GYRO_RANGE,
           info->gyro_bias_wz / 32768.0 * GYRO_RANGE);
}

/* ================================================================
 *  原始数据 → 物理量转换 + 写入CSV
 * ================================================================ */
static void convert_raw_to_physical(const IMUData *raw,
                                    const SensorRangeInfo *info,
                                    IMUDataPhysical *phys)
{
    double acc_scale = info->acc_range * 9.8 / 32768.0;
    double gyro_scale = info->gyro_range / 32768.0;
    double angle_scale = 180.0 / 32768.0;

    phys->ax = raw->ax * acc_scale;
    phys->ay = raw->ay * acc_scale;
    phys->az = raw->az * acc_scale;

    phys->wx = (raw->wx - info->gyro_bias_wx) * gyro_scale;
    phys->wy = (raw->wy - info->gyro_bias_wy) * gyro_scale;
    phys->wz = (raw->wz - info->gyro_bias_wz) * gyro_scale;

    phys->roll  = raw->roll  * angle_scale;
    phys->pitch = raw->pitch * angle_scale;
    phys->yaw   = raw->yaw   * angle_scale;
}

static void convert_and_save_csv(CollectorCtx *ctx)
{
    if (ctx->g_raw_count == 0) {
        fprintf(stderr, "[%s 错误] 没有采集到数据, 无法写入CSV\n", ctx->hand_label);
        return;
    }

    SensorRangeInfo info;
    detect_sensor_ranges(ctx, &info);

    FILE *csv_file = fopen(ctx->csv_path, "w");
    if (!csv_file) {
        perror("Failed to open CSV file");
        return;
    }

    fprintf(csv_file, "# IMU Data [%s] - Auto-converted to physical values\n", ctx->hand_label);
    fprintf(csv_file, "# Acc range: +/-%.0fg, Gyro range: +/-%.0fdeg/s\n",
            info.acc_range, info.gyro_range);
    fprintf(csv_file, "# Gyro bias(raw): wx=%.0f wy=%.0f wz=%.0f\n",
            info.gyro_bias_wx, info.gyro_bias_wy, info.gyro_bias_wz);
    fprintf(csv_file, "# Sample rate: 100Hz\n");
    fprintf(csv_file, "ax_mps2,ay_mps2,az_mps2,wx_dps,wy_dps,wz_dps,roll_deg,pitch_deg,yaw_deg\n");

    IMUDataPhysical phys;
    for (int i = 0; i < ctx->g_raw_count; i++) {
        convert_raw_to_physical(&ctx->g_raw_data[i], &info, &phys);
        fprintf(csv_file, "%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f\n",
                phys.ax, phys.ay, phys.az,
                phys.wx, phys.wy, phys.wz,
                phys.roll, phys.pitch, phys.yaw);
    }

    fclose(csv_file);
    printf("[%s 转换] %d 帧原始数据已转换为物理量并保存到: %s\n",
           ctx->hand_label, ctx->g_raw_count, ctx->csv_path);
    printf("[%s 转换] 加速度: ±%.0fg → m/s², 角速度: ±%.0f°/s (已去零偏), 角度: → °\n",
           ctx->hand_label, info.acc_range, info.gyro_range);
}

/* ================================================================
 *  帧收集线程 (ctx驱动版本)
 * ================================================================ */
static void *frame_collector_ctx(void *arg)
{
    CollectorCtx *ctx = (CollectorCtx *)arg;
    time_t start_time = time(NULL);
    int frame_count = 0;
    unsigned char buf[4096];

    int fd = open(ctx->port, O_RDONLY | O_NOCTTY);
    if (fd < 0) {
        fprintf(stderr, "[%s] Unable to open serial port: %s\n", ctx->hand_label, ctx->port);
        ctx->running = 0;
        pthread_exit(NULL);
    }

    struct termios tty;
    tcgetattr(fd, &tty);
    cfsetospeed(&tty, BAUDRATE);
    cfsetispeed(&tty, BAUDRATE);
    tty.c_cflag &= ~PARENB; tty.c_cflag &= ~CSTOPB; tty.c_cflag &= ~CSIZE; tty.c_cflag |= CS8;
    tty.c_cflag |= CREAD | CLOCAL;
    tty.c_lflag &= ~(ICANON | ECHO | ECHOE | ECHONL | ISIG);
    tty.c_iflag &= ~(IXON | IXOFF | IXANY | IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL);
    tty.c_oflag &= ~OPOST;
    tty.c_cc[VMIN] = 0; tty.c_cc[VTIME] = 0;
    tcsetattr(fd, TCSANOW, &tty);

    while (ctx->running && (time(NULL) - start_time < ctx->target_frames / 100)) {
        fd_set rfd;
        FD_ZERO(&rfd);
        FD_SET(fd, &rfd);
        struct timeval tv = {0, 1000};
        select(fd + 1, &rfd, NULL, NULL, &tv);
        if (!FD_ISSET(fd, &rfd)) continue;

        int n = read(fd, buf, sizeof(buf));
        if (n <= 0) continue;

        for (int i = 0; i < n - 1; i++) {
            if (buf[i] == 0x55 && buf[i+1] == 0x61 && i + 20 <= n) {
                IMUData imu;
                imu.ax    = (int16_t)(buf[i+2]  | (buf[i+3]  << 8));
                imu.ay    = (int16_t)(buf[i+4]  | (buf[i+5]  << 8));
                imu.az    = (int16_t)(buf[i+6]  | (buf[i+7]  << 8));
                imu.wx    = (int16_t)(buf[i+8]  | (buf[i+9]  << 8));
                imu.wy    = (int16_t)(buf[i+10] | (buf[i+11] << 8));
                imu.wz    = (int16_t)(buf[i+12] | (buf[i+13] << 8));
                imu.roll  = (int16_t)(buf[i+14] | (buf[i+15] << 8));
                imu.pitch = (int16_t)(buf[i+16] | (buf[i+17] << 8));
                imu.yaw   = (int16_t)(buf[i+18] | (buf[i+19] << 8));

                if (store_raw_frame(ctx, &imu) != 0) { ctx->running = 0; break; }
                frame_count++;
                i += 19;
            }
        }

        if (frame_count - ctx->g_last_flush >= FLUSH_THRESHOLD) {
            ctx->g_last_flush = frame_count;
            ctx->total_frames = frame_count;
        }
    }

    ctx->total_frames = frame_count;
    ctx->running = 0;
    close(fd);
    pthread_exit(NULL);
}

/* ================================================================
 *  初始化 CollectorCtx
 * ================================================================ */
static void ctx_init(CollectorCtx *ctx, const char *port, const char *hand_label, int collection_time)
{
    memset(ctx, 0, sizeof(CollectorCtx));
    ctx->port = port;
    ctx->hand_label = hand_label;
    ctx->running = 1;
    ctx->target_frames = collection_time * 100;
    ctx->total_frames = 0;
    ctx->g_last_flush = 0;
    ctx->g_raw_data = NULL;
    ctx->g_raw_count = 0;
    ctx->g_raw_capacity = 0;
    generate_csv_path(hand_label, ctx->csv_path);
}

static void ctx_cleanup(CollectorCtx *ctx)
{
    free(ctx->g_raw_data);
    memset(ctx, 0, sizeof(CollectorCtx));
}

/* ================================================================
 *  单IMU采集模式 (向后兼容)
 * ================================================================ */
int collect_data(int argc, char *argv[], char *csv_path_out)
{
    if (argc > 2) {
        fprintf(stderr, "Usage: %s [collection_time_seconds]\n", argv[0]);
        fprintf(stderr, "Default: %d seconds\n", COLLECTION_TIME_SECONDS);
        return 1;
    }

    int collection_time = (argc == 2) ? atoi(argv[1]) : COLLECTION_TIME_SECONDS;
    if (collection_time <= 0) {
        fprintf(stderr, "Invalid collection time. Please provide a positive integer.\n");
        return 1;
    }

    printf("Collecting data for %d seconds...\n", collection_time);
    printf("Collecting data at 100Hz...\n");
    printf("Action: 0-%ds prepare, %d-%ds raise to target height and hold. Do not lower before recording ends.\n",
           PREP_TIME_SECONDS, PREP_TIME_SECONDS, collection_time);

    char port[SERIAL_PATH_MAX];
    if (choose_single_serial_port(port) != 0) {
        return 1;
    }

    CollectorCtx ctx;
    ctx_init(&ctx, port, "H", collection_time);

    printf("[文件] 本次数据将保存到: %s\n", ctx.csv_path);
    if (csv_path_out) {
        strncpy(csv_path_out, ctx.csv_path, CSV_PATH_MAX - 1);
        csv_path_out[CSV_PATH_MAX - 1] = '\0';
    }

    pthread_t collector_thread;
    if (pthread_create(&collector_thread, NULL, (void *)frame_collector_ctx, &ctx) != 0) {
        perror("Failed to create collector thread");
        ctx_cleanup(&ctx);
        return 1;
    }

    printf("[训练] 准备开始，请保持静止。\n");
    time_t prompt_start = time(NULL);
    int raise_prompted = 0;
    while (ctx.running && ctx.total_frames < ctx.target_frames) {
        sleep(1);
        int elapsed = (int)(time(NULL) - prompt_start);
        if (!raise_prompted && elapsed >= PREP_TIME_SECONDS && collection_time > PREP_TIME_SECONDS) {
            printf("[训练] 5秒到，请把手抬起来。\n");
            fflush(stdout);
            raise_prompted = 1;
        }
    }
    ctx.running = 0;
    printf("[训练] %d秒到，停止训练。\n", collection_time);

    pthread_join(collector_thread, NULL);

    printf("\n[系统] 采集完成, 开始转换数据...\n");
    convert_and_save_csv(&ctx);

    ctx_cleanup(&ctx);
    return 0;
}

/* ================================================================
 *  双IMU同步采集模式
 * ================================================================ */
int collect_dual_data(int argc, char *argv[], char *csv_left, char *csv_right)
{
    imu_ensure_data_dir();
    printf("[路径] IMU 数据目录: %s\n", imu_get_data_dir());

    if (argc > 2) {
        fprintf(stderr, "Usage: %s [collection_time_seconds]\n", argv[0]);
        fprintf(stderr, "Default: %d seconds\n", COLLECTION_TIME_SECONDS);
        return 1;
    }

    int collection_time = (argc == 2) ? atoi(argv[1]) : COLLECTION_TIME_SECONDS;
    if (collection_time <= 0) {
        fprintf(stderr, "Invalid collection time. Please provide a positive integer.\n");
        return 1;
    }

    char left_port[SERIAL_PATH_MAX];
    char right_port[SERIAL_PATH_MAX];
    if (choose_serial_ports(left_port, right_port) != 0) {
        return 1;
    }

    printf("============================================================\n");
    printf("  双IMU同步采集模式\n");
    printf("  左手: %s\n", left_port);
    printf("  右手: %s\n", right_port);
    printf("  采集时长: %d 秒 @ 100Hz\n", collection_time);
    printf("  动作流程: 0-%d秒准备, %d-%d秒抬起到目标高度并保持, 采集结束前不要放下\n",
           PREP_TIME_SECONDS, PREP_TIME_SECONDS, collection_time);
    printf("============================================================\n");

    CollectorCtx ctxL, ctxR;
    ctx_init(&ctxL, left_port,  "L", collection_time);
    ctx_init(&ctxR, right_port, "R", collection_time);

    printf("[文件] 左手数据: %s\n", ctxL.csv_path);
    printf("[文件] 右手数据: %s\n", ctxR.csv_path);

    /* 启动两个采集线程 */
    pthread_t threadL, threadR;
    if (pthread_create(&threadL, NULL, (void *)frame_collector_ctx, &ctxL) != 0) {
        perror("Failed to create left collector thread");
        ctx_cleanup(&ctxL);
        ctx_cleanup(&ctxR);
        return 1;
    }
    if (pthread_create(&threadR, NULL, (void *)frame_collector_ctx, &ctxR) != 0) {
        perror("Failed to create right collector thread");
        ctxL.running = 0;
        pthread_join(threadL, NULL);
        ctx_cleanup(&ctxL);
        ctx_cleanup(&ctxR);
        return 1;
    }

    /* 等待两个线程完成 */
    printf("[训练] 准备开始，请保持静止。\n");
    time_t prompt_start = time(NULL);
    int raise_prompted = 0;
    while ((ctxL.running && ctxL.total_frames < ctxL.target_frames) ||
           (ctxR.running && ctxR.total_frames < ctxR.target_frames)) {
        sleep(1);
        int elapsed = (int)(time(NULL) - prompt_start);
        if (!raise_prompted && elapsed >= PREP_TIME_SECONDS && collection_time > PREP_TIME_SECONDS) {
            printf("[训练] 5秒到，请把手抬起来。\n");
            fflush(stdout);
            raise_prompted = 1;
        }
    }
    ctxL.running = 0;
    ctxR.running = 0;
    printf("[训练] %d秒到，停止训练。\n", collection_time);

    pthread_join(threadL, NULL);
    pthread_join(threadR, NULL);

    /* 分别转换和保存 */
    printf("\n[系统] 左手采集完成, 开始转换...\n");
    convert_and_save_csv(&ctxL);
    printf("\n[系统] 右手采集完成, 开始转换...\n");
    convert_and_save_csv(&ctxR);

    /* 输出路径 */
    if (csv_left) {
        strncpy(csv_left, ctxL.csv_path, CSV_PATH_MAX - 1);
        csv_left[CSV_PATH_MAX - 1] = '\0';
    }
    if (csv_right) {
        strncpy(csv_right, ctxR.csv_path, CSV_PATH_MAX - 1);
        csv_right[CSV_PATH_MAX - 1] = '\0';
    }

    ctx_cleanup(&ctxL);
    ctx_cleanup(&ctxR);
    return 0;
}
