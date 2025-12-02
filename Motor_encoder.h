#ifndef SRC_MOTOR_ENCODER_H_
#define SRC_MOTOR_ENCODER_H_

#include "main.h"

#define ENCODER_RESOLUTION 65536
#define PULSES_PER_REVOLUTION (44.0f * 45.0f)
typedef struct {
    float rpm;
    int64_t total_pulses;
    int32_t last_counter_value;
    uint32_t last_time_ms;
    float timer_period_sec;
    TIM_HandleTypeDef *htim_encoder;
    int8_t direction;
    uint8_t first_time;
} encoder_inst;

void Encoder_Update(encoder_inst *enc);
void Encoder_Reset(encoder_inst *enc);

#endif /* SRC_MOTOR_ENCODER_H_ */
