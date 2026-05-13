use anchor_lang::prelude::*;

declare_id!("6RtQVUig8h6DATFBHKGE3Cu2vWoG39Eaak8jVuhKgSzp");

#[account]
#[derive(InitSpace)]
pub struct Registry {
    pub next_incident_id: u64,
    pub authority: Pubkey,
}

#[account]
#[derive(InitSpace)]
pub struct Incident {
    pub id: u64,
    pub occurred_at: u64,
    pub camera_id_hash: [u8; 32],
    #[max_len(16)]
    pub vehicle_class: String,
    pub distance_cm: u32,
    pub ttc_ms: u32,
    pub severity_score: u8,
    #[max_len(16)]
    pub severity_label: String,
    pub alert_flag: bool,
    #[max_len(64)]
    pub clip_cid: String,
    pub reporter: Pubkey,
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone)]
pub struct IncidentInput {
    pub occurred_at: u64,
    pub camera_id_hash: [u8; 32],
    pub vehicle_class: String,
    pub distance_cm: u32,
    pub ttc_ms: u32,
    pub severity_score: u8,
    pub severity_label: String,
    pub alert_flag: bool,
    pub clip_cid: String,
}

#[event]
pub struct IncidentRecorded {
    pub incident_id: u64,
    pub occurred_at: u64,
    pub camera_id_hash: [u8; 32],
    pub vehicle_class: String,
    pub severity_score: u8,
    pub alert_flag: bool,
    pub clip_cid: String,
    pub reporter: Pubkey,
}

#[error_code]
pub enum RegistryError {
    #[msg("Timestamp must be greater than zero")]
    InvalidTimestamp,
    #[msg("Vehicle class is required")]
    VehicleClassRequired,
    #[msg("Clip CID is required")]
    ClipCidRequired,
    #[msg("Severity score must be between 0 and 100")]
    ScoreOutOfRange,
}

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(
        init,
        payer = authority,
        space = 8 + Registry::INIT_SPACE,
        seeds = [b"registry"],
        bump,
    )]
    pub registry: Account<'info, Registry>,
    #[account(mut)]
    pub authority: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(input: IncidentInput)]
pub struct RecordIncident<'info> {
    #[account(
        mut,
        seeds = [b"registry"],
        bump,
    )]
    pub registry: Account<'info, Registry>,

    #[account(
        init,
        payer = reporter,
        space = 8 + Incident::INIT_SPACE,
        seeds = [b"incident", registry.next_incident_id.to_le_bytes().as_ref()],
        bump,
    )]
    pub incident: Account<'info, Incident>,

    #[account(mut)]
    pub reporter: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[program]
pub mod near_miss_registry {
    use super::*;

    pub fn initialize(ctx: Context<Initialize>) -> Result<()> {
        ctx.accounts.registry.next_incident_id = 1;
        ctx.accounts.registry.authority = ctx.accounts.authority.key();
        Ok(())
    }

    pub fn record_incident(ctx: Context<RecordIncident>, input: IncidentInput) -> Result<()> {
        require!(input.occurred_at > 0, RegistryError::InvalidTimestamp);
        require!(
            !input.vehicle_class.is_empty(),
            RegistryError::VehicleClassRequired
        );
        require!(!input.clip_cid.is_empty(), RegistryError::ClipCidRequired);
        require!(input.severity_score <= 100, RegistryError::ScoreOutOfRange);

        let registry = &mut ctx.accounts.registry;
        let incident = &mut ctx.accounts.incident;

        incident.id = registry.next_incident_id;
        incident.occurred_at = input.occurred_at;
        incident.camera_id_hash = input.camera_id_hash;
        incident.vehicle_class = input.vehicle_class.clone();
        incident.distance_cm = input.distance_cm;
        incident.ttc_ms = input.ttc_ms;
        incident.severity_score = input.severity_score;
        incident.severity_label = input.severity_label.clone();
        incident.alert_flag = input.alert_flag;
        incident.clip_cid = input.clip_cid.clone();
        incident.reporter = ctx.accounts.reporter.key();

        registry.next_incident_id += 1;

        emit!(IncidentRecorded {
            incident_id: incident.id,
            occurred_at: incident.occurred_at,
            camera_id_hash: incident.camera_id_hash,
            vehicle_class: incident.vehicle_class.clone(),
            severity_score: incident.severity_score,
            alert_flag: incident.alert_flag,
            clip_cid: incident.clip_cid.clone(),
            reporter: incident.reporter,
        });

        Ok(())
    }
}
