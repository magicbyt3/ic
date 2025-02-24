/* tag::catalog[]
Title:: Basic HTTP requests from canisters

Goal:: Ensure simple HTTP requests can be made from canisters.

Runbook::
0. Instantiate a universal VM with a webserver
1. Instantiate an IC with one application subnet with the HTTP feature enabled.
2. Install NNS canisters
3. Install the proxy canister
4. Make an update call to the proxy canister.

Success::
1. Received http response with status 200.

end::catalog[] */

use crate::canister_http::lib::*;
use crate::driver::{
    test_env::TestEnv,
    test_env_api::{retry_async, RETRY_BACKOFF, RETRY_TIMEOUT},
};
use crate::util::block_on;
use anyhow::bail;
use canister_test::Canister;
use dfn_candid::candid_one;
use ic_cdk::api::call::RejectionCode;
use ic_ic00_types::{CanisterHttpRequestArgs, HttpMethod, TransformType};
use proxy_canister::{RemoteHttpRequest, RemoteHttpResponse};
use slog::{info, Logger};

pub fn test(env: TestEnv) {
    let logger = env.logger();
    let mut nodes = get_node_snapshots(&env);
    let node = nodes.next().expect("there is no application node");
    let runtime = get_runtime_from_node(&node);
    let proxy_canister = create_proxy_canister(&env, &runtime, &node);
    let webserver_ipv6 = get_universal_vm_address(&env);

    block_on(async {
        test_proxy_canister(
            &proxy_canister,
            format!("https://[{webserver_ipv6}]:20443"),
            logger,
        )
        .await;
    });
}

async fn test_proxy_canister(proxy_canister: &Canister<'_>, url: String, logger: Logger) {
    retry_async(&logger, RETRY_TIMEOUT, RETRY_BACKOFF, || async {
        let res =
            proxy_canister
                .update_(
                    "send_request",
                    candid_one::<
                        Result<RemoteHttpResponse, (RejectionCode, String)>,
                        RemoteHttpRequest,
                    >,
                    RemoteHttpRequest {
                        request: CanisterHttpRequestArgs {
                            url: url.to_string(),
                            headers: vec![],
                            body: Some("".as_bytes().to_vec()),
                            transform: Some(TransformType::Function(candid::Func {
                                principal: proxy_canister.canister_id().get().0,
                                method: "transform".to_string(),
                            })),
                            method: HttpMethod::GET,
                            max_response_bytes: None,
                        },
                        cycles: 500_000_000_000,
                    },
                )
                .await
                .expect("Update call to proxy canister failed");
        if !matches!(res, Ok(ref x) if x.status == 200) {
            bail!("Http request failed response: {:?}", res);
        }
        info!(&logger, "Update call succeeded! {:?}", res);
        Ok(())
    })
    .await
    .expect("Timeout on doing a canister http call to the webserver");
}
