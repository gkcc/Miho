use std::{sync::Arc, time::Duration};

use reqwest::Client;
use tokio::time::sleep;

use crate::Result;

#[derive(Clone)]
pub struct HttpClient {
    client: Client,
    retries: usize,
    backoff: Arc<[Duration]>,
}

impl HttpClient {
    pub fn new(timeout: Duration, retries: usize) -> Result<Self> {
        Ok(Self {
            client: Client::builder()
                .timeout(timeout)
                .user_agent("miho-endgame/0.1")
                .build()?,
            retries,
            backoff: [
                Duration::from_millis(250),
                Duration::from_secs(1),
                Duration::from_secs(2),
            ]
            .into(),
        })
    }

    pub async fn get_text(&self, url: &str) -> Result<String> {
        let mut attempt = 0;
        loop {
            match self
                .client
                .get(url)
                .send()
                .await
                .and_then(|r| r.error_for_status())
            {
                Ok(response) => return Ok(response.text().await?),
                Err(error) if attempt < self.retries => {
                    sleep(self.backoff[attempt.min(self.backoff.len() - 1)]).await;
                    attempt += 1;
                    drop(error);
                }
                Err(error) => return Err(error.into()),
            }
        }
    }
}
