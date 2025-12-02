/*
 * pid_control.h
 *
 *  Created on: May 30, 2025
 *      Author: User
 */

#ifndef SRC_PID_CONTROL_H_
#define SRC_PID_CONTROL_H_
#include "stdint.h"

typedef struct{
	float p_gain;
	float i_gain;
	float d_gain;
    float delta_t;
	int16_t last_error;
	int32_t intergral_error;
	int16_t output;
	int32_t intergral_max;
	int16_t output_max;
	int16_t output_min;
}pid_inst_int16_t;

void set_pid_gain(pid_inst_int16_t* pid_instance, float p_gain,float i_gain, float d_gain );
void apply_pid(pid_inst_int16_t* pid_instance,int16_t error);

#endif /* SRC_PID_CONTROL_H_ */
