/**
 * Domain model types and interfaces.
 */

export interface User {
  id: string;
  name: string;
  email: string;
  created_at?: string;
}

export interface Task {
  id: string;
  title: string;
  user_id: string;
  completed: boolean;
  created_at?: string;
}
