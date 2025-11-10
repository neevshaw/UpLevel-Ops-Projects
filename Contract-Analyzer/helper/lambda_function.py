import json
import os
import io
import time
from typing import Any, Dict
import requests
import boto3
import unicodedata
import re
from docx import Document
from openai import OpenAI
import fitz  # PyMuPDF

SCREENING_PROMPT = """
STEP 2: SCREENING

Input: {upload_id, company, contract_type, data:{document_text}}

Process:

Focus on these 9 Legal Review Provisions:

●	Total Contract Value OR Initial Term of Contract exceeds  $20,000.
●	Initial Term exceeds 36 months.
●	Sharing of sensitive data (e.g., customer PII, source code, trade secrets).
●	Restrictive covenants (non‑compete, non‑solicit, exclusivity, MFN).
●	Licensing or joint ownership of BOULEVARD's intellectual property.
●	Use of BOULEVARD, customer, or end‑user data in generative AI tools.
●	Non‑US governing law or dispute forum (if location is in the US - DO NOT FLAG).
●	Any prior, current, or pending disputes with the contracting party
●	Any other material legal or regulatory risk flagged by the Contract Owner or Business Sponsor.

For each criterion, search document_text for matches.

Extract exact snippet (10-30 words) showing the problematic text.

Supply reason demonstrating why the criteria was flagged.

If ANY red flags found → screening_status = "red", next_step = "redline_plan"

If NO red flags → screening_status = "green", next_step = "deliver"

Example Output JSON:
{
"status": "success",
"current_step": "screening",
"next_step": "redline_plan" | "deliver",
"workflow_version": "1.0",
"helper_version": "3.0",
"result_summary": {
"screening_status": "green" | "red",
"triggers": [
{
"type": "Initial Term exceeds 36 months",
"snippet": "Section 6 of the Non-Disclosure Agreement is hereby amended by replacing “second anniversary of the Effective Date” in the second line of such section with “fourth anniversary of the Effective Date”",
"reason": "This contract exceeds the 36 months term limit for the initial term."
}
]
}
}
"""
REDLINE_PLAN = """

STEP 3: REDLINE_PLAN

Input: {upload_id, company, contract_type, data:{document_text}}

In this step you are generating redlines of the given document accoridng to the following guidlines (mainly BLVD_MSA_REDLINE_RULES, because GUIDE TO EFFECTIVE CONTRACT REDLINE COMMENTS is just for good practices).
EXPECTED MINIMUM AMOUNT OF REDLINES (DEPENDING ON CONTRACT_TYPE):
- NDA contracts: 5-10 redlines typical
- MSA contracts: 10-15 redlines typical
- Service agreements: 10-17 redlines typical

# GUIDE TO EFFECTIVE CONTRACT REDLINE COMMENTS:

General Best Practices for Contract Comments

When adding comments to a contract draft for the counterparty, follow these best practices to ensure your remarks are effective and professional:
•	Always accompany substantive changes with a comment: As a rule, every significant edit (insertion, deletion, or revision) should include an explanatory comment . This shows respect and transparency. The comment is your opportunity to justify the change and persuade the other side of its merit. Even if a clause is simply unacceptable, do more than say “deleted” – explain the issue and your reasoning. The only exceptions are truly trivial edits (formatting or obvious typos) which may not warrant a comment (more on exceptions below) 5 .
•	Explain the “why” behind each change: Clearly state why you made the change or cannot accept the original language 6 . Your comment should answer the counterparty’s unspoken question: “What’s the reason for this edit?” Provide enough context so they understand your perspective. For example, if you narrowed a clause’s scope, you might explain that it was too broad and posed a risk to your client, and that your revision addresses that risk in a fair way. If you added a clause, explain what concern or scenario it is meant to cover. The goal is to make your rationale explicit and sensible.
•	Be formal, clear, and professional in tone: Write comments in a polite, legalistic tone that mirrors how lawyers communicate. Use complete sentences and avoid slang or overly casual language. It is often effective to write in the first-person plural (e.g., “We propose…”, “We cannot agree to X because…”), since as counsel you speak on behalf of your client’s side. Stay courteous and factual – do not use accusatory or emotional language. Even if rejecting a term, phrase it diplomatically (e.g., “We are unable to accept this provision because …” rather than “This clause is terrible for us”). Maintain a tone of collaboration and respect.
•	Be concise but informative: Keep comments as brief as possible while still conveying the necessary justification. Long-winded or repetitive comments can be counterproductive – the other side may gloss over them if they read like essays. Aim for a tight paragraph or a few sentences (often 1–3 sentences) focusing on the key point. However, don’t be so terse that your meaning is unclear. For instance, simply stating “Not acceptable” is unhelpful; instead, provide a short reason: “Not acceptable as written because it imposes all liability on one side; we propose making this mutual.” Striking the right balance between brevity and clarity is crucial.
•	Include legal and business justifications: Strengthen your comment by providing the legal rationale (risk, liability, compliance, etc.) and/or the business rationale (business practicalities, fairness, industry norms) for the change 6 . Lawyers often find it persuasive when you cite the legal reason (e.g., “to comply with applicable law” or “to avoid an uninsurable risk”) as well as the business reason (e.g., “to meet our standard policy” or “to ensure both parties are protected”). For example, if you limit liability, your comment might mention that unlimited liability is not workable for either party’s insurance, hence a reasonable cap protects both sides. Including multiple angles of justification shows you’ve thought the issue through and are not changing things arbitrarily 7 .
•	Focus on mutual benefit when possible: Frame your changes in a way that shows how they benefit or at least fairly balance both parties. If you can demonstrate that your edit isn’t just onesided but actually creates a fair outcome, the counterparty will be more receptive. For example, instead of saying “We removed the exclusivity clause because it hurts us,” you might write “Removed the exclusivity requirement to allow both parties the freedom to pursue other opportunities – this keeps the agreement non-binding and fair to both sides.” Highlighting fairness or reciprocity can make the change more palatable. As one expert notes, a comment that appeals to both sides’ interests increases the likelihood your change will be accepted .
•	Use consistent contract terminology: Refer to sections, definitions, and parties exactly as they are used in the contract. This avoids confusion. For example, say “Section 10 (Indemnification)” rather than “that part about damages”. Capitalize defined terms (e.g., “Confidential Information”, “Effective Date”) in your comments just as the contract does. This shows professionalism and precision. It also helps the reader quickly identify which part of the contract you are addressing.
•	Avoid revealing internal strategy or sensitive info: Never include internal deliberations, negotiation strategy, or comments meant for your client’s eyes in the version sent to the counterparty. This may sound obvious, but in practice mistakes happen – a note intended as an internal instruction can accidentally be left in and seen by the other side 9 . To prevent this, confine your comments to externally appropriate content only. For instance, do not write “We actually can live with clause 5 if needed, but let’s ask to delete it first” in a comment – that would undermine your position if the other side sees it. All comments should be drafted with the assumption the counterparty (and potentially their lawyers) will read them. If you need to discuss internally, do it outside of the document (or use a separate internal comment feature if available, to keep it hidden 9 ). In short, filter your comments to contain only what you want the other side to know.
•	Stay objective and avoid inflammatory language: Stick to the facts and the contract at hand. Do not assign blame or use harsh words about the other side’s draft. Even if a clause is one-sided or “unfair,” your comment should address the issue without insult. For example, rather than “This clause is absurdly one-sided,” say “This clause is one-sided in its current form; we propose revisions to balance the obligations of both parties.” Keep the tone professional and solution-oriented.
•	Be mindful of length and readability: If you have multiple points on one clause, consider whether to combine them into one comment or use separate comments for clarity. Usually, one comment per clause is sufficient, but if a clause is being heavily modified, you might break the explanation into bullet points within one comment (if the platform allows) or into two comments targeting specific subsections. Always ask yourself, “Will the counterparty easily grasp our point here?” and format accordingly.
•	Know when not to comment: Not every change requires a comment. There are a few exceptions to the “always comment” rule. Minor edits that do not affect rights or obligations – for example, fixing a typo, correcting punctuation, or standardizing a term’s capitalization – can often be left without comment, especially if they are self-evident to a careful reader 5 8 . Over-commenting on trivial issues can clutter the document and annoy the reader. Use your judgment: if the change is purely stylistic or obviously an error correction, you may omit the comment. (If the other side is likely to wonder why you made even a small change, then a short comment is still warranted.) The guiding principle is to focus comments on substantive changes or anything the other side could question.
•	Follow standard formatting and placement: Insert your comment at the precise location of the change so it’s clear what text it refers to. Typically, using Word’s Track Changes or a similar tool, you highlight or place the cursor on the edited text and add a comment. Ensure the comment remains attached to the relevant clause even if text shifts. If you’re dealing with an entire clause addition or deletion, you might attach the comment to the clause number or title for clarity. Make sure comments are easily visible in the margin (avoid embedding them in-line in the text). The idea is to make it as easy as possible for the counterparty to correlate each comment with the change it explains.

By adhering to these best practices, your comments will read as clear, reasoned explanations rather than arbitrary demands. This collaborative, transparent approach builds credibility and paves the way for more efficient negotiations 3 . The other party is less likely to push back out of confusion or principle when you’ve shown respect and logic in explaining your position.


Commenting on Different Types of Changes
Different kinds of redline edits call for slightly different commenting approaches. Below are guidelines on how to handle comments for additions, deletions, and modifications, as well as other common change scenarios:

When Adding New Content
Scenario: You insert a new clause or new language that wasn’t in the original draft. For example, you might add a sentence to cover a missing definition, a new warranty, or a clarification of obligations.
How to comment: When you add something new, the other side may not immediately know why it’s needed. Your comment should justify the inclusion and explain the gap it fills. Start by indicating what the new content is intended to address. For instance: “Added a definition for ‘Affiliate’ to clarify the scope of parties covered by the agreement.” Then give the reason: “This ensures both parties know which related entities are bound by the confidentiality obligations.” Another example: “Inserted a clause requiring commercially reasonable efforts to deliver on time, to set a clear performance standard.” The comment could add: “This addition provides mutual assurance, as it binds both parties to a reasonable performance obligation, preventing ambiguity.” Always frame it as adding clarity, balance, or necessary protection – never as an attempt to sneak in a one-sided advantage. If the addition is for compliance or legal reasons, definitely mention that (e.g., “Added [Clause] to ensure compliance with new data privacy regulations effective as of 2025”). If it’s a business requirement, state it plainly (“Added a termination for convenience right for our company, as this is a standard requirement in our service contracts to allow flexibility”). By preemptively explaining an insertion, you reduce the chance that the counterparty will view it with suspicion or confusion.

When Deleting or Removing Text
Scenario: You delete a clause or strike certain language that the other party had in the draft. This is inherently a rejection of something they proposed, so it can be sensitive.
How to comment: It is critical to be diplomatic and clear when explaining deletions, since you are effectively saying “no” to the other side’s text. First, identify what you removed if it’s not obvious. For example: “Removed the indemnity for XYZ in Section 12.” Next, give a reasoned justification: “because it was overly broad – it would make our company liable for matters outside our control. We can only accept liability for issues within our scope of work.” Notice this explains the concern in factual terms. If possible, offer an alternative or a compromise in the comment, which shows you are trying to reach a middle ground: “We removed the unlimited indemnification obligation as drafted, but we are open to a mutual indemnity where each party indemnifies the other for its own breaches or negligence.” This way, you’re not just saying “no”; you’re proposing a solution. Another example: “Deleted the auto-renewal provision because our policy is to renegotiate renewals rather than automatic extension. We prefer a mutual opt-in at renewal.” Here you clearly state why the deletion was made (company policy) and what you prefer instead. Always couch the deletion in terms of issue with the clause, not the drafter – e.g., “the provision is problematic because [reason],” rather than “your clause is bad.” Keep the tone impersonal and focused on the text. By providing a solid justification, you show respect for what was there and give the counterparty something to consider instead of leaving them defensive.

When Revising or Modifying Wording
Scenario: You change some wording in an existing clause – for instance, altering a few terms, tightening or loosening obligations, or rephrasing for clarity. The core concept remains, but you propose it in different words.
How to comment: Explain what change you made and why it improves the clause. If you modified an obligation or standard, clarify the effect: e.g., “Revised ‘best efforts’ to ‘reasonable efforts’ in Section 5 to align with a more objective and standard performance obligation.” Then the reason: “’Reasonable efforts’ is a commonly accepted standard and is more definable, which will help both parties avoid uncertainty 8 .” If you edited wording for clarity, say so: “Reworded the termination clause for clarity, ensuring it’s clear what events allow termination. This rewrite doesn’t change intent, but makes the obligations more precise.” If your revision does change the intent, highlight the rationale: “Adjusted the limitation of liability to carve out breaches of confidentiality from the liability cap – this change is to ensure that in the event of a data breach, full damages can be claimed despite the cap, which is important for protecting sensitive information.” In that case, a comment might read: “Modified the liability clause to exclude confidential information breaches from the liability cap, because such breaches need full recourse due to the severity of harm they can cause.” When modifying language, it’s also helpful to use comparative phrasing in your comment (old vs new) so the reader immediately grasps the difference. For example: “Changed ‘30 days’ to ‘45 days’ for invoice payment terms to give our accounts payable sufficient processing time.” This way, even without scrutinizing the redline markup, the other side sees what the change is and why it’s being requested. Always emphasize that the new wording is meant to make the contract more balanced, clear, or fair. If the revision benefits both sides (or at least doesn’t unfairly prejudice the other side), be sure to point that out in your explanation.

When Adjusting Formatting or Defined Terms
Scenario: You make non-substantive edits like fixing grammar, punctuation, capitalization, or consistency of defined terms (e.g., capitalizing the word “Agreement” when used as a defined term).
How to comment: Most purely stylistic or clerical edits don’t need a comment, especially if they’re obvious. For example, if you capitalized “Agreement” throughout to match how defined terms are treated, that change speaks for itself to a reader experienced in contracts 8 . Likewise, correcting “teh” to “the” or adding a missing comma for grammar typically doesn’t require explanation. Over-commenting these can clutter the document. However, use judgment: if a formatting change might be misinterpreted, you can add a brief note. For instance, if you renumbered sections or re-ordered definitions alphabetically, you might comment, “Reordered definitions alphabetically for ease of reference – no content changes made.” This reassures the other side that nothing sneaky was introduced in the formatting. In general, reserve comments for things that affect meaning. If it’s purely cosmetic and will be obvious to the counterparty, you can safely implement it without comment 5 . Just double-check that it truly cannot be misconstrued as a substantive change.

By tailoring your commenting approach to the type of change, you ensure that each comment is relevant and useful. Always put yourself in the shoes of the counterparty – what would you want to know if you saw this change coming from them? That perspective will guide you in writing comments that are responsive to their likely questions or objections.


Examples of Good Contract Comments

To illustrate these principles, below are a few examples of effective redline comments in different situations. Each example assumes a scenario and shows a sample comment that follows the guidelines:
•	Example 1 – Narrowing Scope (Non-Disclosure Agreement Purpose Clause): Suppose you edit an NDA’s purpose clause to limit use of confidential information only to evaluating a specific project.
    Comment: “Narrowed the definition of Purpose to use confidential information solely for evaluating the [Project]. This change protects both parties by ensuring information isn’t used for any unrelated purposes, aligning with the intent of the NDA.”
    Why it’s good: The comment clearly states what was changed (the scope of “Purpose”) and why (to protect both parties and stick to intended use). It highlights a mutual benefit, increasing the chance of acceptance 8 .
•	Example 2 – Deletion with Alternative (Liability/Indemnity Clause): You delete a clause that required your client to indemnify the other party for all losses, and replace it with a mutual indemnity clause.
    Comment: “Removed the one-way indemnification in Section 10, as it would make us liable for all losses even beyond our control. We’ve proposed mutual indemnification instead, so each party covers losses arising from its own actions. This balances the risk equally between us.”
    Why it’s good: The comment explains the deletion (“one-way indemnification” removed) and why (unfair burden on one side). It then immediately proposes a solution (mutual indemnity) and frames it as balancing risk, which is a fair outcome. It’s polite and focuses on the clause, not blaming the other side for trying.
•	Example 3 – Modification (Limitation of Liability): You modify a limitation of liability clause to exclude certain types of damages or to set a cap.
    Comment: “Adjusted the liability clause to exclude indirect damages (like lost profits) and set a liability cap at $100,000. This is in line with standard practice to prevent unlimited exposure. It ensures neither party is liable for unlimited or unforeseeable losses, which keeps the risk at a reasonable level for both of us.”
    Why it’s good: It details the specific changes (no indirect damages, cap of $100K) and provides a rationale referencing standard practice and mutual benefit (neither side has unlimited risk). The tone is neutral and focuses on fairness and reasonableness.
Each of these examples demonstrates a few key qualities of good contract comments: specificity about the change, a clear explanation of why it was made, and a respectful, neutral tone. Tailor your actual comments to the specifics of your contract, but these samples show the general approach in action.




# BLVD_MSA_REDLINE_RULES:
1.	Intellectual Property Ownership and Use of Boulevard Data
    ●	Rule (IF/THEN):
        ○	IF the contract addresses ownership of the vendor’s platform, THEN state that the vendor solely owns its services/products and associated intellectual property and that Boulevard receives only the rights expressly set forth in the agreement; ELSE reject language implying broader rights to Boulevard.
        ○	IF the vendor seeks rights to use Boulevard data beyond providing the services, THEN allow use only of data derived from use of the services that is anonymized and aggregated so it does not directly or indirectly identify Boulevard, its users, customers, or any natural person, and is subject to applicable law; ELSE prohibit.
        ○	IF the clause permits vendor disclosure/sale/assignment/lease/commercial exploitation of Boulevard data, THEN require prior written approval from Boulevard; ELSE reject.
        ○	IF a deliverable (e.g., report, document, tool, customization, etc.) is being provided as part of the services, THEN require ownership or broad usage license of the deliverable by Boulevard.
    ●	Allowed:
        ○	Vendor’s ownership of its own platform and intellectual property as stated.
        ○	Vendor’s use of aggregated and anonymized derived data that cannot directly or indirectly identify Boulevard or a natural person, subject to law.
    ●	Not Allowed:
        ○	Any vendor use of Boulevard data that is identifiable (directly or indirectly) or not derived/aggregated/anonymized, other than as expressly permitted to provide the services .
        ○	Any implied rights in Boulevard data beyond what is expressly permitted.
        ○	Disclosure/sale/lease/assignment or commercial exploitation of Boulevard data without prior written Boulevard approval.
    ●	Gray Area Handling:
        ○	[FLAG] Vague term: “anonymized” and “aggregated” — needs Boulevard definitions and minimum technical standard (e.g., differential privacy or k-anonymity thresholds).
            ■	Anonymized means the data does not identify and cannot reasonably be used to identify or re-identify any individual, including when combined with other reasonably available data
                ●	Note to Uplevel – we don’t necessarily need “anonymized” to be defined in contracts, so this is not a redline we’d want created, but are providing the definition so the AI has it.
    ●	Definitions (if used):
        ○	Boulevard Data = all data shared by Boulevard, directly or indirectly, with the vendor.
        ○	Vendor IP = vendor services/products and all underlying technology and associated intellectual property rights.

2.	 Use of Boulevard Trademarks / Publicity
    ●	Rule (IF/THEN):
        ○	IF the vendor requests to use Boulevard’s name, trademarks, service marks, logos, or to publicize the relationship, THEN require prior written consent and include a No Publicity clause covering media releases, websites, sales/marketing materials, interviews, and employee/agent communications; ELSE reject.
        ○	IF the vendor requests mutuality, THEN replace “Vendor will not use…” with “Neither party will use the other party’s (or its Affiliates’) name or trademarks without prior written consent.”
    ●	Allowed:
        ○	Mutual, written-consent requirement for any publicity/mark usage.
    ●	Not Allowed:
        ○	Any publicity, logo use, case studies, or name-dropping without Boulevard’s prior written approval.
    ●	Gray Area Handling:
        ○	[FLAG] Vague term: “Affiliates” — needs house definition/reference to defined term.
            ■	Note to Uplevel – “Affiliates” will likely be defined within the agreement. If it is not, let’s define “Affiliates” as, “any other entity that directly or indirectly controls, is controlled by, or is under common control with Vendor and that has been designated to receive Services under this Agreement.” 

3.	Term (Automatic Renewal)
    ●	Rule (IF/THEN):
        ○	IF automatic renewal is included, THEN set renewals to one (1) year terms and allow either party to opt out with at least 30 days’ prior written notice before the next Renewal Term; ELSE remove auto-renewal.
    ●	Allowed:
        ○	1-year auto-renewals with at least a 30-day non-renewal notice.
    ●	Not Allowed:
        ○	Auto-renewal with a non-renewal right of 30-days.
    ●	Gray Area Handling:
        ○	[FLAG] Boulevard’s acceptable minimum notice is 30 days
    ●	Definitions (if used):
        ○	Renewal Term = each automatic one-year extension following the Initial Term.


4.	Termination by Boulevard without Cause (Convenience)
    ●  	Rule (IF/THEN):
        ○	IF vendor rejects Boulevard’s 30-day convenience termination right, THEN offer extended notice in sequence: 60 days, then 90 days; ELSE keep 30 days.
        ○	This extended notice applies to both the MSA and all outstanding SOWs/Orders.
    ●	Allowed:
        ○	Convenience termination with 30 days; if resisted, 60/90 escalation only as needed.
    ●	Not Allowed:
        ○	Any notice period longer than 120 days for convenience termination.

5.	Termination with Cause
    ●	Rule (IF/THEN):
        ○	IF a party materially breaches, THEN the non-breaching party may terminate for cause if breach is uncured within 30 days after detailed written notice.
        ○	IF the breach is incurable, tHEN no cure period applies and termination may be immediate.
    ●	Allowed:
        ○	30-day cure for curable material breaches; immediate termination for incurable events.
    ●	Not Allowed:
        ○	Extending cure beyond 30 days without Boulevard approval; prohibiting immediate termination for cyber breach or insolvency.


6.	 Effect of Termination
    ●	Rule (IF/THEN):
        ○	IF the agreement terminates, THEN (i) vendor ceases services; (ii) undisputed pre-termination amounts remain due per contract; (iii) all licenses/authorizations terminate; (iv) within 30 days, each party must return or destroy the other’s Confidential Information, except for retention required by law/accounting or archival backups; and (v) both parties provide commercially reasonable support for an orderly wind-down.
    ●	Allowed:
        ○	30-day return/destruction with narrow legal/backup exceptions; wind-down cooperation.
    ●	Not Allowed:
        ○	Retaining live copies of Confidential Information beyond legal/backup exceptions after 30 days.
    ●	Gray Area Handling:
        ○	[FLAG] Vague term: “commercially reasonable support” — define scope (e.g., hours cap, transition assistance tasks).
            ■	Note to Uplevel – “commercially reasonable support” is a commonly enough used phrase in contracts.
    ●	Source Trace:
        ○	within 30 days… return or destroy all Confidential Information… exceptions for legal/accounting or archived backups… commercially reasonable support to wind down.

7.	Right to Audit and Payment Adjustment
    ●	Rule (IF/THEN):
        ○	IF appropriate under Boulevard’s thresholds, THEN the audit right may be removed from the agreement.
            ■	THRESHOLDS:
                ●	If the Contract involves Client Data, PHI, AI, significant IP rights, the audit right may NOT be removed from the agreement, and 
                ●	If the Contract value is $100k or more, the audit right may NOT be removed from the agreement.
    ●	Allowed:
        ○	Removal of audit clause where thresholds/criteria warrant.
    ●	Not Allowed:
        ○	N/A


8.	Representations and Warranties (Remedy Limitation on IP Warranty)
    ●	Rule (IF/THEN):
        ○	IF including vendor’s IP non-infringement warranty, THEN cap Boulevard’s remedy for breach of that specific warranty to vendor’s indemnification obligations in the agreement; ELSE reject broader remedies language that conflicts with this limitation.
        ○	IF general warranty disclaimers are proposed, THEN accept a mutual disclaimer of implied warranties (merchantability/fitness) so long as the express warranties in the agreement remain intact.
    ●	Allowed:
        ○	The Sole remedy for IP warranty breach is indemnification obligations (as referenced to a section).
        ○	Mutual disclaimer of implied warranties.
    ●	Not Allowed:
        ○	Disclaiming all warranties where no service-specific express warranties exist.
    ●	Gray Area Handling:
        ○	[FLAG] Cross-reference needed: replace “Section XX” with the correct indemnification section number/citation.
            ■	Note to UpLevel - the Section # is dependent on each contract and the AI should make sure that it is updating all references to sections throughout the contract if any section numbers are changed.

9.	Limitation of Liability (Excluded Claims, Ordinary Cap, Super Cap)
    ●	Rule (IF/THEN):
        ○	IF including consequential damages waiver, THEN include mutual waiver of indirect, special, incidental, or consequential damages (including lost profits/revenue/opportunities).
        ○	IF a liability cap is used, THEN set the Ordinary Cap to the total amount paid by Boulevard to vendor in the 12 months prior to when damages were incurred plus any then-payable but unpaid fees.
        ○	IF the claim falls within Excluded Claims (fraud, gross negligence, or willful misconduct; indemnity obligations; breach of confidentiality and data protection/data security obligations), THEN apply a Super Cap equal to 5× the Ordinary Cap; ELSE apply the Ordinary Cap.
    ●	Allowed:
        ○	12-month fees Ordinary Cap; 5× Super Cap for Excluded Claims; mutual consequential damages waiver.
    ●	Not Allowed:
        ○	Caps below the 12-month fees level for ordinary claims; applying the Ordinary Cap to Excluded Claims.
    ●	Gray Area Handling:
        ○	[FLAG] Cross-references needed: replace placeholders with actual section numbers for confidentiality/data security and indemnity.
            ■	Note to UpLevel - the Section # is dependent on each contract and the AI should make sure that it is updating all references to sections throughout the contract if any section numbers are changed.
    ●	Definitions (if used):
        ○	Excluded Claims = fraud, gross negligence, or willful misconduct; indemnity; breach of confidentiality; breach of data protection/data security obligations, including any DPA (Data Processing Agreement).
        ○	Ordinary Cap = 12-month fees paid before damage accrual + fees then payable but unpaid.
        ○	Super Cap = 5× the Ordinary Cap.


10.	Indemnity (Gross Negligence Standard; Comparative Fault)
    ●	Rule (IF/THEN):
        ○	IF mutual indemnities are included, THEN each party indemnifies the other for third-party claims arising out of: (a) fraud, gross negligence, bad faith, or willful misconduct of the indemnifying party; (b) claims that the indemnifying party’s services/products/technology/content/materials/data/trademarks, when used as permitted, infringe or misappropriate third-party intellectual property; and (c) the indemnifying party’s material breach of the agreement.
        ○	IF responsibility for Losses is allocated, THEN prorate the indemnifying party’s financial responsibility to exclude the proportion caused or contributed by the indemnified party.
    ●	Allowed:
        ○	Gross-negligence standard in the indemnity trigger; IP infringement indemnity; comparative fault proration.
    ●	Not Allowed:
        ○	Refusing IP infringement indemnity for vendor-provided technology/content.
        ○	Imposing full indemnity where the indemnified party contributed to the Loss.
    ●	Definitions (if used):
        ○	Losses = claims, costs, liabilities, damages, judgments, and reasonable attorneys’ fees.

11.	Applicable Law and Venue (Split Venue)
    ●	Rule (IF/THEN):
        ○	IF a split-venue fallback is used, THEN (i) Vendor-initiated proceedings must be brought exclusively in Los Angeles County, California (state or federal courts), and (ii) Boulevard-initiated proceedings must be brought in the vendor’s chosen venue (to be specified).
        ○	IF choice of law is addressed, THEN apply Delaware law (without conflict-of-laws rules) as selected in the contract.
        ○	Include a mutual jury-trial waiver.
    ●	Allowed:
        ○	LA-exclusive venue for vendor-initiated suits; mutual jury waiver; CA/NY governing law.
    ●	Not Allowed:
        ○	Vendor-initiated suits outside LA County, CA.
        ○	Governing law outside CA/DE/NY without Legal approval.
    ●	Gray Area Handling:
        ○	[FLAG] Missing value: insert the vendor’s chosen venue for Boulevard-initiated actions.
            ■	This value will vary on a case-by-case basis and will be provided in the contract if it applies. If it is not provided in the contract, do not include it. 
        ○	[FLAG] Decision needed: which of CA/DE/NY will Boulevard select for the governing law in this deal.
            ■	Note to UpLevel: If we default it to DE, can we make it so the AI adds as a comment to any redlines, “We will also accept CA or NY governing law”?
    
## Topics flagged (rightmost column unclear in provided paste):

12.	Services and Fees
    ●	AI Action Rule —
        ○	Require every Statement of Work (SOW) to include: party legal names; reference to the master agreement; effective date; detailed scope and deliverables; start date and term; detailed fee schedule; payment terms of NET 30; uptime and customer support Service Level Agreements (SLAs); and signatures for both parties. Insert any missing items.
        ○	Enforce price locks for the SOW term. Delete any vendor right to increase prices during the term unless Boulevard has a concurrent right to terminate for convenience without penalty; if such termination right is not present, insert it.
        ○	Insert explicit timelines, milestones, acceptance criteria, approval points, and measurable performance metrics where absent or vague.
        ○	Add service credits/penalties tied to measurable failures (e.g., credits for late deliverables or missed SLAs). Leave [FLAG] comments where credit amounts/caps must be set.
        ○	Align Services and Fees text to match Boulevard’s deal understanding; revise ambiguous drafting for precision.
    ●	Allowed:
        ○	NET 30 payment terms.
        ○	Price locks for the SOW term.
        ○	Documented SLAs and measurable acceptance criteria.
        ○	Service credits/penalties for missed milestones.
    ●	Not Allowed:
        ○	Unilateral price increases during the SOW term without a termination right for Boulevard.
        ○	Ambiguous scopes, timelines, or acceptance criteria.
    ●	Definitions (if used):
        ○	SOW = Statement of Work.
        ○	SLA = Service Level Agreement.

13.	Relationship Between the Parties
    ●	AI Action Rule:
        ○	State that the agreement creates no partnership, joint venture, agency, or fiduciary relationship. Insert this if missing.
        ○	State that neither party may bind the other or incur obligations on the other’s behalf without prior written consent. Insert this if missing.
        ○	Delete or revise any language implying partnership, joint venture, agency, or authority to bind.
    ●	Allowed:
        ○	Independent-contractor relationship acknowledgement.
    ●	Not Allowed:
        ○	Any implication of partnership, joint venture, agency, or authority to bind the other party.

14.	Confidential Information
    ●	AI Action Rule:
        ○	Require each party to protect the other’s Confidential Information using the care used for its own similar information but at least a commercially reasonable standard of care . Strengthen weaker standards.
        ○	Limit use and disclosure to performance under the agreement or exercise of granted rights, including disclosures to representatives with a need to know who are legally bound to protect the information. Insert this scoping where missing.
        ○	For compelled disclosure, insert advance notice (to the extent permitted by law) and reasonable cooperation at the discloser’s expense.
        ○	Add express entitlement to injunctive and other equitable relief for actual or threatened breaches.
        ○	Make confidentiality obligations survive termination for so long as any Confidential Information remains in the receiving party’s possession and meets the “Confidential Information” definition; add if missing.
        ○	Insert a comprehensive definition of Confidential Information, including catch-all language “information that the receiving party knows or should reasonably know is confidential or proprietary”, with standard exclusions (public domain without breach; known without restriction before disclosure; rightfully disclosed by a third party without restriction; independently developed without use of the other party’s Confidential Information).
        ○	Insert prompt notice and cooperation obligations upon unauthorized disclosure or security incident involving Confidential Information, consistent with the Data Security section.
        ○	If the agreement states a lower confidentiality standard, redline to the baseline above; if broader vendor rights are granted (e.g., reuse for unrelated purposes), narrow to the baseline above or delete.
    ●	Allowed:
        ○	Sharing with representatives under written confidentiality obligations and need-to-know limitations.
        ○	Retaining legal/archival copies as required by law or policy, subject to ongoing confidentiality.
    ●	Not Allowed:
        ○	Using Confidential Information outside the scope of the agreement.
        ○	Disclosing Confidential Information without authorization or legal compulsion.

15.	Data Security
    ●	AI Action Rule: 
        ○	If it is missing, Insert a data security clause requiring administrative, physical, and technical safeguards consistent with industry standards and appropriate to the data processed.
        ○	Define “Data Breach” as unauthorized access causing destruction, loss, alteration, disclosure, acquisition, or access to personal data, and require breach notification within 72 hours with iterative updates on scope, root cause, counts/categories, geographies, and remediation; include a duty to provide reasonable assistance.
        ○	State that security obligations continue post-termination while any personal data or Confidential Information remains in a party’s possession.
        ○	Cross-reference Confidential Information obligations to avoid gaps.
        ○	If the agreement provides weaker security, redline to baseline; if notice obligations are vague or missing, insert specific timing and details.
    ●	Allowed:
        ○	Use of established security frameworks and documented incident response procedures.
        ○	Providing breach details promptly and supplementing information as it becomes available.
    ●	Not Allowed:
        ○	Processing personal data without appropriate safeguards.
        ○	Delaying breach notification beyond 72 hours.
    ●	Definitions (if used):
        ○	Data Breach = unauthorized access causing destruction, loss, alteration, disclosure, acquisition, or access to personal data.

16.	Compliance with Laws
    ●	AI Action Rules:
        ○	Require mutual compliance with all applicable federal, state, local, and foreign laws and regulations in performance of the agreement. Strengthen or insert as needed.
        ○	Delete any carve-outs that excuse compliance with applicable law.
    ●	Allowed:
        ○	Mutual compliance obligations.
    ●	Not Allowed:
        ○	Carve-outs that excuse non-compliance with applicable law.

17.	Survival of Obligations
    ●	AI Action Rules:
        ○	Include a survival clause listing at minimum: confidentiality, indemnification, limitation of liability, dispute resolution, and intellectual property provisions.
        ○	Add a catch-all so provisions that by their nature should survive will continue after termination/expiration.
        ○	Insert cross-references to the correct section numbers; if missing, add placeholders with [FLAG] to be updated.
    ●	Allowed:
        ○	Explicit survival list in the agreement text.
    ●	Not Allowed:
        ○	Omission of survival for confidentiality or intellectual property provisions.
    ●	Gray Area Handling:
        ○	[FLAG] Provide final section numbers for the survival list.
            ■	Note to Contract Analyzer - the Section # is dependent on each contract and the AI should make sure that it is updating all references to sections throughout the contract if any section numbers are changed.

18.	Insurance
    ●	AI Action Rule
        ○	Require vendor to maintain commercially reasonable insurance with reputable carriers, including commercial general liability, professional/errors & omissions, workers’ compensation, and cyber liability coverage sufficient for contractual obligations. 
        ○	Require certificates of insurance (COIs) upon request and additional insured status for Boulevard where applicable; include notice of cancellation, non-renewal, or material change obligations.
        ○	State that insurance does not limit or replace vendor’s contractual obligations or liability.
        ○	If insurance language is missing or weaker, insert/strengthen to baseline; if one-sided, make mutual where appropriate.
    ●	Allowed:
        ○	Reasonable lines of coverage aligned to services provided.
        ○	COIs provided upon request with additional insured status where applicable.
    ●	Not Allowed:
        ○	Refusal to provide proof of insurance or notice of material changes.
    ●	Definitions (if used):
        ○	COI = Certificate of Insurance.
19.	Non-Solicitation
    ●	AI Action Rule:
        ○	If a non-solicitation provision is present, please do the following:
            ■	(A) limit it to (1) year post-terimation of employees that were introduced to Boulevard as part of the contracted services, and
            ■	(B) limit it to a prohibition against directly soliciting that individual (but allow for that individual to respond to a general Boulevard open position notice)
    ●	Allowed:
        ○	Non-solicitation with a one-year duration of relevant individuals regarding direct solicitation..
    ●	Not Allowed:
        ○	Non solicits longer than 1 year post termination
        ○	Non solicits generally covering all hire activity
        ○	Non solicits covering non-employees, like contractors and service providers and customers
20.	Notices
    ●	AI Action Rule:
        ○	Authorize email as a valid and sufficient method for formal notices to designated contacts; retain physical mail/courier as optional secondary methods only.
        ○	Insert specific notice email addresses and physical addresses for both parties, with a mechanism for updating by written notice. Include legal@blvd.co. for Boulevard.
        ○	Add deemed-receipt timing (e.g., email upon transmission if no bounce; courier upon delivery).
        ○	Delete requirements that restrict formal notice to certified mail or courier only.
    ●	Allowed:
        ○	Email as a valid and sufficient formal notice method.
    ●	Not Allowed:
        ○	Requiring certified mail or courier as the only acceptable notice method.


21.	Assignment
    ●	AI Action Rule: 
        ○	Prohibit vendor from assigning the agreement or delegating obligations without Boulevard’s prior written consent.
        ○	Allow mutual assignment without consent to a successor via merger or sale of all/substantially all assets if the assignee agrees in writing to be bound and is not a competitor; require prompt notice of such assignment.
        ○	Delete language permitting assignment to competitors or without assumption of obligations.
        ○	If assignment is one-sided, make the change-of-control exception mutual on equivalent terms unless Legal directs otherwise.
    ●	Allowed:
        ○	Change-of-control assignment to a non-competitor with assumption of obligations and prompt notice.
    ●	Not Allowed:
        ○	Assignments to competitors or assignments without assumption of obligations.

22.	Force Majeure
    ●	AI Action Rule: 
        ○	Insert a force majeure clause covering events beyond a party’s reasonable control (including labor disputes, shortages, denial-of-service, telecom failures, pandemics, governmental orders, war/terrorism/riot, acts of God).
        ○	Extend performance deadlines for the duration of the event and prorate fees for impacted periods; add both if missing.
        ○	Require the affected party to use commercially reasonable efforts to continue and resume performance promptly.
    ●	Allowed:
        ○	Extension of deadlines equal to the period of delay.
        ○	Fee proration during the impacted period.
    ●	Not Allowed:
        ○	Charging full fees where services are not provided due to force majeure without proration.

23.	Waiver
    ●	AI Action Rule: 
        ○	State that no failure or delay to exercise rights constitutes a waiver and that waivers must be in a signed writing; insert or strengthen as needed.
        ○	Clarify that section headings do not affect interpretation.
    ●	Allowed:
        ○	Written, specific waivers only.
    ●	Not Allowed:
        ○	Implied or blanket waivers based on past practice.

24.	Attorneys’ Fees
    ●	AI Action Rule: 
        ○	If there is a one-sided fee provision favoring the vendor, delete the one-sided fee provision favoring the vendor.
    ●	Allowed:
        ○	Mutual prevailing-party fee shifting to discourage frivolous claims.
    ●	Not Allowed:
        ○	One-sided fee-shifting in favor of the vendor.

25.	Severability
    ●	AI Action Rule: 
        ○	Insert severability: any unenforceable provision is modified to the minimum extent necessary to be enforceable; the remainder continues in full force and effect.
    ●	Allowed:
        ○	Judicial modification to preserve enforceability.
    ●	Not Allowed:
        ○	Voidance of the entire agreement due to one unenforceable clause.

26.	Entire Agreement
    ●	AI Action Rule: 
        ○	Insert integration clause stating the master agreement (with orders/SOWs and exhibits) is the entire agreement and supersedes prior or contemporaneous understandings (written or oral) regarding the subject matter.
        ○	State that external information or advice does not create warranties or obligations; require amendments in a written instrument signed by both parties.
        ○	Delete side-letter or oral modification language.
    ●	Allowed:
        ○	Integration clause covering prior sales materials and NDAs where appropriate.
    ●	Not Allowed:
        ○	Oral modifications or side letters not executed by both parties.

27.	Arbitration – Equitable Relief Carve-Out (Playbook)
    ○	AI Action Rule: 
        i.	If there is a arbitration or dispute resolution provision:
            1.	Scope. There must be a carve-out for injunctive/equitable claims
                a.	E.g. All claims arising out of or relating to the Agreement or the parties’ relationship except injunctive/equitable claims.
                b.	E.g. Either party may seek temporary, preliminary, or permanent injunctive relief or other equitable remedies (including specific performance) in court. Such action does not waive arbitration of damages/merits claims. No bond requirement (or “bond waived to the extent permitted by law”).

            2.	Forum/Rules: JAMS (Comprehensive Rules) or AAA (Commercial Rules).

            3.	Seat/Venue: Must match Governing Law Section

            
EXAMPLE OUTPUT JSON (ONE ENTRY IN PLAN FOR EACH PROPOSED REDLINE):
Output:
{
  "status": "success",
  "current_step": "redline_plan",
  "next_step": "apply_redlines",
  "result_summary": {
    "plan": [
        {
            "issue": "Auto-renewal exceeds permitted one-year term",
            "rationale": "Playbook requires auto-renewals to be for one (1) year with at least 30 days’ non-renewal notice",
            "comment": "Aligning auto-renewal length to one year per standard; separate edit addresses notice period if needed",
            "fallback_position": "If resisted, accept 12-month renewals with 45 days’ notice but not longer terms",
            "edit_spec": {
            "type": "replace",
            "surrounding_text": "This Agreement will automatically renew for additional two (2) year terms unless either party provides written non-renewal notice at least thirty (30) days prior to the end of the then-current term.",
            "find": "two (2) year",
            "replace": [
                { "text": "one (1) year" }
            ]
            }
        },
        {
            "issue": "Publicity allowed without prior written consent",
            "rationale": "Vendor may not use Boulevard’s name, marks, or publicize the relationship without prior written consent; mutuality acceptable",
            "comment": "Adding mutual, written-consent requirement directly after the publicity permission sentence",
            "fallback_position": "If vendor demands examples, allow pre-approved logo/style guide use strictly per a mutually agreed brand guideline",
            "edit_spec": {
            "type": "insert_text",
            "adjacent_text": "Vendor may list Boulevard as a customer in press releases, marketing materials, case studies, and online postings without approval from Boulevard or its representatives.",
            "insert_pos": "after",
            "insert": [
                {
                "text": " Neither party will use the other party’s (or its Affiliates’) name, trademarks, service marks, logos, or otherwise publicize the relationship without prior written consent."
                }
            ]
            }
        },
        {
            "issue": "Missing 72-hour data breach notice and security baseline",
            "rationale": "Agreement must require administrative, physical, and technical safeguards and breach notification within 72 hours with iterative updates",
            "comment": "Inserting a new paragraph to establish security obligations and prompt breach notice",
            "fallback_position": "If 72 hours is resisted, accept 96 hours with rolling updates and reasonable assistance obligations",
            "edit_spec": {
            "type": "insert_paragraph",
            "adjacent_text": "Vendor will implement industry standard safeguards without specific notice obligations to Boulevard.",
            "insert_pos": "after",
            "insert": [
                {
                "text": "Security and Incident Notice. Each party will maintain administrative, physical, and technical safeguards appropriate to the nature of data processed and consistent with industry standards. The receiving party will notify the disclosing party of any confirmed Data Breach without undue delay and in no event later than seventy-two (72) hours after discovery, and will provide ongoing updates on scope, root cause, affected data categories and counts, geographies, and remediation, and will provide reasonable assistance to support investigation and mitigation."
                }
            ],
            "is_list_item": false,
            "list_level": 0
            }
        }
    ]
  }
}

EDIT_SPEC TYPE MATRIX (STRICT)

Allowed edit_spec types: "replace" | "insert_text" | "insert_paragraph"

type="replace"  (for tracked replacement within a paragraph)
REQUIRES: surrounding_text, find, replace
FORBIDS: insert_pos, insert, is_list_item, list_level

type="insert_text"  (for inserting text immediately before/after an anchor string)
REQUIRES: (adjacent_text OR surrounding_text), insert_pos ∈ {"before","after"}, insert (array of runs)
FORBIDS: find, replace
NOTES: adjacent_text should be a unique 10–30 word span in the same paragraph as the insertion point.

type="insert_paragraph"  (for inserting a new paragraph)
REQUIRES: (adjacent_text OR surrounding_text), insert_pos ∈ {"before","after"}, insert (array of runs)
OPTIONAL: is_list_item (boolean, default false), list_level (integer, default 0)
FORBIDS: find, replace
NOTES: For insert_pos="before": adjacent_text must match the START of the target paragraph (first 10–30 words).
       For insert_pos="after": adjacent_text must match the END of the target paragraph (last 10–30 words).

"""

"""
def _normalize_spaces(t: str) -> str:
    # collapse whitespace and normalize unicode quotes
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"\\s+", " ", t)
    return t.strip()

def _extract_paragraph_window(text: str, needle: str, window: int = 160):
    text_norm = _normalize_spaces(text)
    needle_norm = _normalize_spaces(needle)
    i = text_norm.lower().find(needle_norm.lower())
    if i == -1:
        return None
    start = max(0, i - window//2)
    end = min(len(text_norm), i + len(needle_norm) + window//2)
    return text_norm[start:end]
"""

# -----------------------------
# AWS + OpenAI Setup
# -----------------------------
s3 = boto3.client("s3")
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

HELPER_MODEL = os.environ.get("HELPER_MODEL", "gpt-4o-mini")
WORKFLOW_VERSION = "1.1"
HELPER_VERSION = "3.1"
WORD_DOC_GENERATOR_URL = os.environ.get(
    "WORD_DOC_GENERATOR_URL",
    "https://cugpx3dhg7.execute-api.us-west-2.amazonaws.com/default/wordDocGenerator/editFileUpload"
)

# -----------------------------
# Document Retrieval
# -----------------------------
def get_document_text(upload_id: str) -> str:
    bucket = os.getenv("TMP_DOC_UPLOAD_BUCKET_NAME", "tmp-word-doc-upload")
    key = upload_id
    obj = s3.get_object(Bucket=bucket, Key=key)
    body_bytes = obj["Body"].read()
    content_type = str(obj.get("ContentType", "").lower())
    
    # Detect if PDF
    if "pdf" in content_type:
        # Wrap bytes in BytesIO
        doc = fitz.open(stream=io.BytesIO(body_bytes), filetype="pdf")
        
        text_chunks = []
        for page_num, page in enumerate(doc):
            text = page.get_text()  # Try without "text" parameter first
            if text and text.strip():  # Check if text is not just whitespace
                text_chunks.append(text)
        
        doc.close()
        
        if not text_chunks:
            print("⚠️ No text extracted from PDF - might be image-based or encrypted")
            return ""
        
        text = "\n".join(text_chunks)
        return text
    
    # DOCX path
    elif "word" in content_type:
        file_stream = io.BytesIO(body_bytes)
        doc = Document(file_stream)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return text
    else:
        raise ValueError("Unsupported file type or unable to auto-detect type.")


# -----------------------------
# Helper → WordDocGenerator Coordination
# -----------------------------
"""
def call_word_doc_generator(upload_id, edits):
    payload = {
        "upload_id": upload_id,
        "author": "Boulevard Contract Analyzer",
        "track_changes": True,
        "edits": edits,
    }
    resp = requests.post(WORD_DOC_GENERATOR_URL, json=payload, timeout=30)
    resp.raise_for_status()
    print(resp.json())
    return resp.json()


def adjust_failed_edits(upload_id: str, failed_items: list):
    doc_text = get_document_text(upload_id)
    adjusted = []

    for item in failed_items:
        e = item.get("edit_spec", item)  # support either shape
        find_raw = e.get("find", "")

        # Generate candidates: raw, trimmed punctuation variants, straight/curly quotes
        quotes = [
            ("“", "\""), ("”", "\""), ("‘", "'"), ("’", "'")
        ]
        punct_tails = ["", ".", ",", "”", ".”", ",”"]
        candidates = set()
        base = _normalize_spaces(find_raw)
        candidates.add(base)
        for lq, sq in quotes:
            candidates.add(base.replace(lq, sq).replace(lq, sq))
        for tail in punct_tails:
            candidates.add((base + tail).strip())

        chosen = None
        for cand in candidates:
            win = _extract_paragraph_window(doc_text, cand)
            if win:
                chosen = (cand, win)
                break

        # If nothing matched, try a looser token subset (first 2–3 words)
        if not chosen:
            tokens = base.split()
            for n in (3, 2):
                if len(tokens) >= n:
                    loose = " ".join(tokens[:n])
                    win = _extract_paragraph_window(doc_text, loose)
                    if win:
                        chosen = (loose, win)
                        break

        # If still nothing, keep original (it will fail again but we report it)
        if chosen:
            cand, win = chosen
            e["find"] = cand
            e["surrounding_text"] = win

        adjusted.append(e)

    return adjusted



def apply_redlines_with_retry(upload_id, edits):
    for attempt in range(3):
        try:
            result = call_word_doc_generator(upload_id, edits)
            failed = result.get("failed_items", [])
            if not failed:
                return {
                    "status": "success",
                    "applied": result.get("applied", len(edits)),
                    "failed": 0,
                    "failed_items": [],
                }

            # Relax anchors for retry
            edits = adjust_failed_edits(failed)
            time.sleep(min(2 ** attempt * 0.5, 5))
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(min(2 ** attempt * 0.5, 5))

    return {
        "status": "partial_success",
        "applied": 0,
        "failed": len(edits),
        "failed_items": edits,
    }


# -----------------------------
# Helper Envelope & Utilities
# -----------------------------
def _load_helper_prompt():
    p = os.environ.get("HELPER_SYSTEM_PROMPT")
    if p:
        return p
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "helper_system_prompt.txt"), "r", encoding="utf-8") as f:
        return f.read()
"""

HELPER_SYSTEM_PROMPT = {"screening": SCREENING_PROMPT, "redline_plan": REDLINE_PLAN}


def _resp(status: int, body: Dict[str, Any]):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _error_envelope(step: str, error_type: str, error_msg: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "current_step": step or "",
        "next_step": "",
        "workflow_version": WORKFLOW_VERSION,
        "helper_version": HELPER_VERSION,
        "result_summary": {
            "error_type": error_type,
            "error_msg": error_msg
        }
    }


def _success_envelope(step: str, summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "success",
        "current_step": step,
        "next_step": "",
        "workflow_version": WORKFLOW_VERSION,
        "helper_version": HELPER_VERSION,
        "result_summary": summary,
    }
"""
def _validate_envelope(step: str, out: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure required top-level keys exist (or set safe defaults)
    out.setdefault("status", "success")
    out.setdefault("current_step", step or "")
    out.setdefault("next_step", "")
    out["workflow_version"] = WORKFLOW_VERSION
    out["helper_version"] = HELPER_VERSION

    rs = out.get("result_summary", {})
    if not isinstance(rs, dict):
        return _error_envelope(step, "schema_validation_failed", "result_summary must be an object")

    status = out.get("status")

    # Screening step: allow old or new shapes
    if step == "screening" and status in {"success", "partial_success"}:
        has_old = ("screening_status" in rs) and ("triggers" in rs)
        has_new = ("legal_required" in rs) and ("flags" in rs)
        if not (has_old or has_new):
            return _error_envelope(
                step,
                "schema_validation_failed",
                "screening must include either (screening_status & triggers) or (legal_required & flags)"
            )

    # Apply-redlines step: tolerate helper returning compact summary
    if step == "apply_redlines" and status in {"success", "partial_success", "retry"}:
        # Some callers expect applied/failed arrays; make sure keys exist
        rs.setdefault("applied", rs.get("applied", [] if isinstance(rs.get("applied"), list) else []))
        rs.setdefault("failed", rs.get("failed", [] if isinstance(rs.get("failed"), list) else []))
        out["result_summary"] = rs

    return out

"""
def split_text_into_chunks(text: str, j: int, max_words: int = 1000) -> list[str]:
    """Split text into chunks by word count"""
    words = text.split()
    chunk = ' '.join(words[max_words*j:max_words*j + max_words])
    return chunk

# -----------------------------
# Main Lambda Entry Point
# -----------------------------
def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    try:
        raw = event.get("body", "{}")
        if not isinstance(raw, str):
            raw = json.dumps(raw)
        body = json.loads(raw)
    except Exception as e:
        return _resp(400, _error_envelope("", "invalid_body", f"Cannot parse body: {e}"))

    step = body.get("step")
    payload = body.get("payload", {})
    if not step or not payload:
        return _resp(400, _error_envelope("", "missing_field", "step and payload required"))

    try:
        if step == "screening":
            upload_id = payload.get("upload_id")
            document_text = get_document_text(upload_id)
            payload.setdefault("data", {})["document_text"] = document_text

            # Call model for summary
            return call_model(step, payload)

        elif step == "redline_plan":
            upload_id = payload.get("upload_id")
            document_text = split_text_into_chunks(get_document_text(upload_id), j=payload['data'].get("cursor"))
            payload.setdefault("data", {})["document_text"] = document_text
            return call_model(step, payload)

        elif step == "apply_redlines":
            upload_id = payload.get("upload_id")
            edits = payload.get("data", {}).get("edits", [])
            # result = apply_redlines_with_retry(upload_id, edits)
            # return _resp(200, _success_envelope(step, result))

        elif step == "deliver":
            upload_id = payload.get("upload_id")
            filename = payload.get("filename")
            return _resp(200, _success_envelope(step, {"download_url": f"https://cugpx3dhg7.execute-api.us-west-2.amazonaws.com/default/wordDocGenerator/document?upload_id={upload_id}&source=uploaded&filename={filename}"})) 

        else:
            return _resp(400, _error_envelope(step, "unknown_step", f"Unrecognized step: {step}"))

    except Exception as e:
        print(f"Helper error: {e}")
        return _resp(500, _error_envelope(step, "helper_runtime_error", str(e)))



# -----------------------------
# OpenAI Helper Model Call
# -----------------------------
def call_model(step, payload):
    """Call the helper model, then validate/normalize the envelope before returning."""
    user_msg = json.dumps(payload, ensure_ascii=False)
    print("Start")
    chat = client.chat.completions.create(
        model=HELPER_MODEL,
        messages=[
            {"role": "system", "content": HELPER_SYSTEM_PROMPT[step]},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=1000
    )
    content = (chat.choices[0].message.content or "").strip()
    out = json.loads(content)
    if step == "screening":
        out['result_summary']['num_chunks'] = len(payload['data']['document_text'].split(' '))//1000
    print(out)

    return _resp(200, out)


