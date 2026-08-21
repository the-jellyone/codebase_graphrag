/**
 * Centralised API client and endpoint registry.
 */
import { Task } from "../models/types";

export const ENDPOINTS = {
  USERS: "/api/users",
  TASKS: "/api/tasks",
} as const;

const BASE_URL = process.env.API_BASE_URL || "http://localhost:8000";

export async function get(url: string): Promise<Task> {
  const response = await fetch(`${BASE_URL}${url}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });

  if (!response.ok) {
    throw new Error(`GET request failed with status: ${response.status}`);
  }

  return response.json();
}

export async function post(url: string, data: unknown): Promise<any> {
  const response = await fetch(`${BASE_URL}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`POST request failed with status: ${response.status}`);
  }

  return response.json();
}
