/**
 * User service handling API interaction for user entities.
 */
import * as client from "../api/client";
import { User } from "../models/types";

export async function getUser(userId: string): Promise<User> {
  const endpoint = `${client.ENDPOINTS.USERS}/${userId}`;
  const data = await client.get(endpoint);
  return data as unknown as User;
}

export async function createUser(name: string, email: string): Promise<User> {
  const endpoint = client.ENDPOINTS.USERS;
  const data = await client.post(endpoint, { name, email });
  return data as User;
}
