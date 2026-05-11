// Browser-side equivalent of cobot_voice/task_manager_dispatcher.py.
// Calls /task/start (std_srvs/srv/Trigger) over rosbridge_websocket
// instead of `ros2 service call`, so v2 keeps the dispatch behaviour
// without a Python helper.
import { Ros, Service } from "roslib";
import type { SessionOrder } from "./session";

const START_SERVICE = "/task/start";
const SERVICE_TYPE = "std_srvs/srv/Trigger";

export type DispatchResult = {
  ok: boolean;
  message: string;
};

type TriggerRequest = Record<string, never>;
type TriggerResponse = { success?: boolean; message?: string };

let rosInstance: Ros | null = null;
let connectingTo: string | null = null;
let connectPromise: Promise<Ros> | null = null;

function connect(url: string): Promise<Ros> {
  if (rosInstance && connectingTo === url) {
    return Promise.resolve(rosInstance);
  }
  if (connectPromise && connectingTo === url) return connectPromise;

  if (rosInstance) {
    try {
      rosInstance.close();
    } catch {
      /* noop */
    }
    rosInstance = null;
  }

  connectingTo = url;
  const ros = new Ros({ url });

  connectPromise = new Promise<Ros>((resolve, reject) => {
    const onConnect = () => {
      cleanup();
      rosInstance = ros;
      resolve(ros);
    };
    const onError = (event: unknown) => {
      cleanup();
      const detail =
        event && typeof event === "object" && "message" in event
          ? String((event as { message: unknown }).message)
          : String(event);
      reject(new Error(`rosbridge connect failed (${url}): ${detail}`));
    };
    const onClose = () => {
      cleanup();
      reject(new Error(`rosbridge connection closed before ready (${url})`));
    };
    const cleanup = () => {
      ros.off("connection", onConnect);
      ros.off("error", onError);
      ros.off("close", onClose);
    };

    ros.on("connection", onConnect);
    ros.on("error", onError);
    ros.on("close", onClose);
  });

  return connectPromise;
}

export async function dispatchToTaskManager(
  order: SessionOrder,
  rosbridgeUrl: string,
  timeoutMs = 5000,
): Promise<DispatchResult> {
  if (!order?.success) {
    return {
      ok: false,
      message: "Order missing or success=false; not triggering /task/start",
    };
  }

  let ros: Ros;
  try {
    ros = await connect(rosbridgeUrl);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.warn(message);
    return { ok: false, message };
  }

  const service = new Service<TriggerRequest, TriggerResponse>({
    ros,
    name: START_SERVICE,
    serviceType: SERVICE_TYPE,
  });

  return await new Promise<DispatchResult>((resolve) => {
    const timer = setTimeout(() => {
      resolve({
        ok: false,
        message: `${START_SERVICE} timed out after ${timeoutMs}ms`,
      });
    }, timeoutMs);

    service.callService(
      {} as TriggerRequest,
      (response) => {
        clearTimeout(timer);
        if (response?.success) {
          resolve({ ok: true, message: response.message ?? "" });
        } else {
          resolve({
            ok: false,
            message:
              response?.message || `${START_SERVICE} returned success=false`,
          });
        }
      },
      (failure) => {
        clearTimeout(timer);
        resolve({
          ok: false,
          message: `${START_SERVICE} call failed: ${failure}`,
        });
      },
    );
  });
}
