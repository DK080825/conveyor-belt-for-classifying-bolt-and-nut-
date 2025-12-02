/*
 * pid_control.c
 *
 *  Created on: May 30, 2025
 *      Author: User
 */
#include "pid_control.h"

void set_pid_gain(pid_inst_int16_t* pid_instance, float p_gain,float i_gain, float d_gain ){
	pid_instance->p_gain = p_gain;
	pid_instance->i_gain = i_gain;
	pid_instance->d_gain = d_gain;
}
void apply_pid(pid_inst_int16_t* pid_instance,int16_t error){
	pid_instance->intergral_error += error;
	if(pid_instance->intergral_error> pid_instance->intergral_max){
		pid_instance->intergral_error = pid_instance->intergral_max;
	}
	if(pid_instance->intergral_error< -pid_instance->intergral_max){
			pid_instance->intergral_error = -pid_instance->intergral_max;
	}
	pid_instance->output = (int16_t)(pid_instance->p_gain*error + (pid_instance->i_gain)*(pid_instance->intergral_error)
			*(pid_instance->delta_t) + (pid_instance->d_gain)*((error - pid_instance->last_error)/pid_instance->delta_t));

	if(pid_instance->output > pid_instance->output_max){
		pid_instance->output = pid_instance->output_max;
	}
	if(pid_instance->output < pid_instance->output_min){
		pid_instance->output = pid_instance->output_min;
	}
	pid_instance->last_error = error;
}


