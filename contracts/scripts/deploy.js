/**
 * DAHAO Contracts Deployment Script
 *
 * Deploys the full DAHAO governance stack:
 * 1. DAHAOForwarder - ERC2771 forwarder for meta-transactions
 * 2. DAHAOToken - ERC20Votes governance token
 * 3. DAHAOGovernor - Governance contract with gasless voting support
 *
 * Usage:
 *   # Local hardhat network
 *   npx hardhat run scripts/deploy.js
 *
 *   # Avalanche Fuji testnet
 *   npx hardhat run scripts/deploy.js --network fuji
 *
 * Prerequisites:
 *   1. Set PRIVATE_KEY in .env file
 *   2. Ensure account has AVAX for gas (get from faucet for testnet)
 */

const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();

  console.log("=".repeat(60));
  console.log("DAHAO Contracts Deployment");
  console.log("=".repeat(60));
  console.log();
  console.log(`Network: ${hre.network.name}`);
  console.log(`Chain ID: ${(await hre.ethers.provider.getNetwork()).chainId}`);
  console.log(`Deployer: ${deployer.address}`);

  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`Balance: ${hre.ethers.formatEther(balance)} AVAX/ETH`);
  console.log();

  // 1. Deploy DAHAOForwarder
  console.log("1. Deploying DAHAOForwarder...");
  const DAHAOForwarder = await hre.ethers.getContractFactory("DAHAOForwarder");
  const forwarder = await DAHAOForwarder.deploy();
  await forwarder.waitForDeployment();
  const forwarderAddress = await forwarder.getAddress();
  console.log(`   DAHAOForwarder deployed to: ${forwarderAddress}`);

  // 2. Deploy DAHAOToken
  console.log("2. Deploying DAHAOToken...");
  const DAHAOToken = await hre.ethers.getContractFactory("DAHAOToken");
  const token = await DAHAOToken.deploy(deployer.address);
  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();
  console.log(`   DAHAOToken deployed to: ${tokenAddress}`);

  // Verify token details
  const tokenName = await token.name();
  const tokenSymbol = await token.symbol();
  const totalSupply = await token.totalSupply();
  console.log(`   Token: ${tokenName} (${tokenSymbol})`);
  console.log(`   Total Supply: ${hre.ethers.formatEther(totalSupply)} DAHAO`);

  // 3. Deploy DAHAOGovernor
  console.log("3. Deploying DAHAOGovernor...");
  const DAHAOGovernor = await hre.ethers.getContractFactory("DAHAOGovernor");
  const governor = await DAHAOGovernor.deploy(tokenAddress, forwarderAddress);
  await governor.waitForDeployment();
  const governorAddress = await governor.getAddress();
  console.log(`   DAHAOGovernor deployed to: ${governorAddress}`);

  // Verify governor settings
  const votingDelay = await governor.votingDelay();
  const votingPeriod = await governor.votingPeriod();
  console.log(`   Voting Delay: ${votingDelay} blocks (~${Number(votingDelay) / 7200} days @ 12s/block)`);
  console.log(`   Voting Period: ${votingPeriod} blocks (~${Number(votingPeriod) / 7200} days @ 12s/block)`);

  // Summary
  console.log();
  console.log("=".repeat(60));
  console.log("Deployment Summary");
  console.log("=".repeat(60));
  console.log();
  console.log("Contract Addresses:");
  console.log(`  DAHAOForwarder: ${forwarderAddress}`);
  console.log(`  DAHAOToken:     ${tokenAddress}`);
  console.log(`  DAHAOGovernor:  ${governorAddress}`);
  console.log();

  // Output for config.yaml
  console.log("Add to config.yaml:");
  console.log("```yaml");
  console.log("chain:");
  console.log("  type: evm");
  console.log(`  chain_id: ${(await hre.ethers.provider.getNetwork()).chainId}`);
  console.log(`  rpc_url: ${hre.network.config.url || "http://127.0.0.1:8545"}`);
  console.log(`  governor_address: "${governorAddress}"`);
  console.log(`  token_address: "${tokenAddress}"`);
  console.log(`  forwarder_address: "${forwarderAddress}"`);
  console.log("```");
  console.log();

  // Delegate tokens to self for voting power
  console.log("4. Delegating tokens to deployer for voting power...");
  const delegateTx = await token.delegate(deployer.address);
  await delegateTx.wait();
  const votingPower = await token.getVotes(deployer.address);
  console.log(`   Voting power: ${hre.ethers.formatEther(votingPower)} DAHAO`);

  console.log();
  console.log("Deployment complete!");
  console.log();

  // Next steps
  console.log("Next Steps:");
  console.log("1. Update config.yaml with the contract addresses above");
  console.log("2. Distribute tokens to test voters");
  console.log("3. Have voters delegate their tokens (token.delegate(voterAddress))");
  console.log("4. Create a test proposal via DAHAOGovernor");
  console.log("5. Test gasless voting via DAHAO Observer Mode");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
