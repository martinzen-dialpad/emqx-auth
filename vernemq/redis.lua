-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

-- Redis Configuration, read the documentation below to properly
-- provision your database.
require "auth/auth_commons"

-- In order to use this Lua plugin you must store a JSON Object containing
-- the following properties as Redis Value:
--
--  - passhash: STRING (bcrypt)
--  - publish_acl: [ACL]  (Array of ACL JSON Objects)
--  - subscribe_acl: [ACL]  (Array of ACL JSON Objects)
--
-- 	The JSON array passed as publish/subscribe ACL contains the ACL objects topic
-- 	for this particular user. MQTT wildcards as well as the variable
-- 	substitution for %m (mountpoint), %c (client_id), %u (username) are allowed
-- 	inside a pattern.
--
-- The Redis Key is the JSON Array [mountpoint, client_id, username]
--
-- IF YOU USE THE KEY/VALUE SCHEMA PROVIDED ABOVE NOTHING HAS TO BE CHANGED
-- IN THE FOLLOWING SCRIPT.
-- Helper function to fetch and decode ACL from Redis
function fetch_acl(mountpoint, username)
    if username == nil then
        print("[fetch_acl] username is nil")
        return nil
    end
    local key = json.encode({ mountpoint, "*", username })
    print("[fetch_acl] key=" .. key)
    local res = redis.cmd(pool, "get", key)
    if res then
        local acl = json.decode(res)
        print("[fetch_acl] decoded ACL: " .. json.encode(acl))
        return acl
    end
    print("[fetch_acl] no ACL found in Redis")
    return nil
end

function auth_on_register(reg)
    -- Authentication bypassed - using webhook instead
    print("[auth_on_register] bypassing authentication for username=" .. tostring(reg.username))
    return true
end

function auth_on_subscribe(sub)
    print("[auth_on_subscribe] username=" .. tostring(sub.username) .. ", client_id=" .. tostring(sub.client_id))
    local acl = fetch_acl(sub.mountpoint, sub.username)
    if acl then
        -- Clear any existing cache for this client to force fresh lookup every time
        auth_cache.clear_cache(sub.mountpoint, sub.client_id)

        -- Update cache with fresh ACL
        cache_insert(sub.mountpoint, sub.client_id, sub.username, acl.publish_acl, acl.subscribe_acl)

        -- Now check each topic against the updated cache
        for _, topic_qos_pair in ipairs(sub.topics) do
            local topic = topic_qos_pair[1]
            -- Handle both MQTT v3/v4 (qos is number) and v5 (qos is in nested array)
            local qos = topic_qos_pair[2]
            if type(qos) == "table" then
                qos = qos[1]  -- Extract QoS from nested structure in MQTT v5
            end
            print("[auth_on_subscribe] checking topic=" .. topic .. ", qos=" .. tostring(qos))
            local result = auth_cache.match_subscribe(sub.mountpoint, sub.client_id, topic, qos)
            print("[auth_on_subscribe] match_subscribe result=" .. tostring(result))
            if result == false then
                print("[auth_on_subscribe] returning false")
                return false
            end
        end
        print("[auth_on_subscribe] returning true")
        return true
    end
    print("[auth_on_subscribe] returning false (no ACL)")
    return false
end

function auth_on_publish(pub)
    print("[auth_on_publish] username=" .. tostring(pub.username) .. ", client_id=" .. tostring(pub.client_id) .. ", topic=" .. pub.topic)
    local acl = fetch_acl(pub.mountpoint, pub.username)
    if acl then
        -- Clear any existing cache for this client to force fresh lookup every time
        auth_cache.clear_cache(pub.mountpoint, pub.client_id)

        -- Update cache with fresh ACL
        cache_insert(pub.mountpoint, pub.client_id, pub.username, acl.publish_acl, acl.subscribe_acl)

        -- Now check the publish against the updated cache
        local result = auth_cache.match_publish(
            pub.mountpoint,
            pub.client_id,
            pub.topic,
            pub.qos,
            pub.payload,
            pub.retain
        )
        print("[auth_on_publish] match_publish result=" .. tostring(result))
        return result
    end
    print("[auth_on_publish] returning false (no ACL)")
    return false
end

pool = "auth_redis"
config = {
    pool_id = pool
}

redis.ensure_pool(config)
hooks = {
    auth_on_register = auth_on_register,
    auth_on_publish = auth_on_publish,
    auth_on_subscribe = auth_on_subscribe,
    on_unsubscribe = on_unsubscribe,
    on_client_gone = on_client_gone,
    on_client_offline = on_client_offline,
    on_session_expired = on_session_expired,

    auth_on_register_m5 = auth_on_register,
    auth_on_publish_m5 = auth_on_publish,
    auth_on_subscribe_m5 = auth_on_subscribe,
}
