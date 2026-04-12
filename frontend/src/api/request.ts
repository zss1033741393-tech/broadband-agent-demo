import axios, { AxiosError, AxiosResponse } from 'axios';
import { message as antdMessage } from 'antd';
import type { ApiResponse } from '@/types/api';

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

request.interceptors.response.use(
  (response: AxiosResponse<ApiResponse<unknown>>) => {
    const { code, message } = response.data;
    if (code !== 0) {
      antdMessage.error(message || '请求失败');
      return Promise.reject(new Error(message || `业务错误 ${code}`));
    }
    return response;
  },
  (error: AxiosError) => {
    const msg =
      (error.response?.data as ApiResponse<unknown> | undefined)?.message ||
      error.message ||
      '网络错误';
    antdMessage.error(msg);
    return Promise.reject(error);
  },
);

/** 提取 data 字段的便捷封装 */
export async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const res = await request.get<ApiResponse<T>>(url, { params });
  return res.data.data;
}

export async function post<T>(url: string, body?: unknown): Promise<T> {
  const res = await request.post<ApiResponse<T>>(url, body);
  return res.data.data;
}

export async function patch<T>(url: string, body?: unknown): Promise<T> {
  const res = await request.patch<ApiResponse<T>>(url, body);
  return res.data.data;
}

export async function del<T>(url: string): Promise<T> {
  const res = await request.delete<ApiResponse<T>>(url);
  return res.data.data;
}

export default request;
