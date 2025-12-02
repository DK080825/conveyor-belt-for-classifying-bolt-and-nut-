/*
 * queue
 *
 *  Created on: Nov 26, 2025
 *      Author: User
 */
#include "queue.h"

uint8_t queue[QUEUE_SIZE];
volatile uint8_t head = 0;
volatile uint8_t tail = 0;

void Queue_Init(void)
{
    head = 0;
    tail = 0;
}
void Queue_Push(uint8_t data)
{
    uint8_t next = (head + 1) % QUEUE_SIZE;
    if (next != tail)
    {
        queue[head] = data;
        head = next;
    }
}

uint8_t Queue_Pop(void)
{
    uint8_t data = 0;
    if (head != tail)
    {
        data = queue[tail];
        tail = (tail + 1) % QUEUE_SIZE;
    }
    return data;
}

uint8_t Queue_IsEmpty(void)
{
    return (head == tail);
}

