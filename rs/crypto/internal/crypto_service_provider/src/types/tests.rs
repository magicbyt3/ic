#![allow(clippy::unwrap_used)]
use super::*;
use ic_crypto_internal_seed::Seed;
use ic_crypto_internal_test_vectors::ed25519::{
    TESTVEC_ED25519_STABILITY_1_SIG, TESTVEC_RFC8032_ED25519_1_SIG, TESTVEC_RFC8032_ED25519_2_SIG,
    TESTVEC_RFC8032_ED25519_SHA_ABC_PK, TESTVEC_RFC8032_ED25519_SHA_ABC_SIG,
    TESTVEC_RFC8032_ED25519_SHA_ABC_SK,
};
use ic_crypto_internal_test_vectors::multi_bls12_381::TESTVEC_MULTI_BLS12_381_1_PK;
use ic_crypto_internal_test_vectors::unhex::hex_to_byte_vec;
use ic_crypto_internal_threshold_sig_bls12381::dkg::secp256k1::types::{
    EphemeralKeySetBytes, EphemeralPopBytes, EphemeralPublicKeyBytes, EphemeralSecretKeyBytes,
};
use ic_crypto_internal_threshold_sig_bls12381::ni_dkg::groth20_bls12_381::types::{
    BTENode, FsEncryptionKeySet, FsEncryptionSecretKey,
};
use ic_crypto_internal_threshold_sig_bls12381::ni_dkg::types::CspFsEncryptionKeySet;
use ic_crypto_internal_threshold_sig_ecdsa::{
    EccCurveType, MEGaPrivateKey, MEGaPrivateKeyK256Bytes, MEGaPublicKeyK256Bytes,
};
use ic_crypto_internal_types::curves::bls12_381::{Fr as FrBytes, G1 as G1Bytes, G2 as G2Bytes};
use ic_crypto_internal_types::encrypt::forward_secure::groth20_bls12_381::{
    FsEncryptionPok, FsEncryptionPublicKey,
};
use ic_crypto_secrets_containers::SecretArray;
use ic_interfaces::crypto::CryptoHashableTestDummy;
use ic_protobuf::registry::crypto::v1::AlgorithmId as AlgorithmIdProto;
use ic_protobuf::registry::crypto::v1::PublicKey as PublicKeyProto;
use ic_types::crypto::{AlgorithmId, BasicSig, BasicSigOf, UserPublicKey};
use std::convert::TryFrom;
use strum::EnumCount;

fn sk_ed25519_bytes(key: &CspSecretKey) -> Option<&[u8; 32]> {
    match key {
        CspSecretKey::Ed25519(bytes) => Some(bytes.0.expose_secret()),
        _ => None,
    }
}

#[test]
fn should_return_correct_ed25519_secret_key_bytes_for_ed25519_secret_key() {
    let ed25519_csp_sk = CspSecretKey::ed25519_from_hex(TESTVEC_RFC8032_ED25519_SHA_ABC_SK);

    assert_eq!(
        sk_ed25519_bytes(&ed25519_csp_sk).unwrap().to_vec(),
        hex_to_byte_vec(TESTVEC_RFC8032_ED25519_SHA_ABC_SK)
    );
}

#[test]
fn should_return_no_ed25519_secret_key_bytes_for_non_ed25519_secret_key() {
    let secret_key = CspSecretKey::MultiBls12_381(multi_types::SecretKeyBytes(
        [0u8; multi_types::SecretKeyBytes::SIZE],
    ));
    assert!(sk_ed25519_bytes(&secret_key).is_none())
}

#[test]
fn should_redact_csp_secret_key_ed25519_debug() {
    let cspsk_ed25519 = CspSecretKey::Ed25519(ed25519_types::SecretKeyBytes(
        SecretArray::new_and_dont_zeroize_argument(&[1u8; ed25519_types::SecretKeyBytes::SIZE]),
    ));
    assert_eq!(
        "CspSecretKey::Ed25519 - REDACTED",
        format!("{:?}", cspsk_ed25519)
    );
}

#[test]
fn should_redact_csp_secret_key_multi_debug() {
    let cspsk_multi = CspSecretKey::MultiBls12_381(multi_types::SecretKeyBytes(
        [1u8; multi_types::SecretKeyBytes::SIZE],
    ));
    assert_eq!(
        "CspSecretKey::MultiBls12_381 - REDACTED",
        format!("{:?}", cspsk_multi)
    );
}

#[test]
fn should_redact_csp_secret_key_thres_debug() {
    let cspsk_thresh = CspSecretKey::ThresBls12_381(threshold_types::SecretKeyBytes(
        [1u8; threshold_types::SecretKeyBytes::SIZE],
    ));
    assert_eq!(
        "CspSecretKey::ThresBls12_381 - REDACTED",
        format!("{:?}", cspsk_thresh)
    );
}

#[test]
fn should_redact_csp_secret_key_secp_debug() {
    let cspsk_secp = CspSecretKey::Secp256k1WithPublicKey(EphemeralKeySetBytes {
        secret_key_bytes: EphemeralSecretKeyBytes([1u8; EphemeralSecretKeyBytes::SIZE]),
        public_key_bytes: EphemeralPublicKeyBytes([1u8; EphemeralPublicKeyBytes::SIZE]),
        pop_bytes: EphemeralPopBytes([1u8; EphemeralPopBytes::SIZE]),
    });
    assert!(format!("{:?}", cspsk_secp).contains("secret_key: REDACTED"));
}

#[test]
fn should_redact_csp_secret_key_tls_ed25519_debug() {
    let cspsk_tls = CspSecretKey::TlsEd25519(TlsEd25519SecretKeyDerBytes {
        bytes: vec![1u8; 3],
    });
    assert_eq!(
        "CspSecretKey::TlsEd25519 - REDACTED",
        format!("{:?}", cspsk_tls)
    );
}

#[test]
fn should_redact_csp_secret_key_fs_encryption_debug() {
    let cspsk_fs = CspSecretKey::FsEncryption(CspFsEncryptionKeySet::Groth20_Bls12_381(
        FsEncryptionKeySet {
            public_key: FsEncryptionPublicKey(G1Bytes([1u8; G1Bytes::SIZE])),
            secret_key: FsEncryptionSecretKey {
                bte_nodes: vec![
                    BTENode {
                        tau: vec![1, 2, 3],
                        a: G1Bytes([1; G1Bytes::SIZE]),
                        b: G2Bytes([1; G2Bytes::SIZE]),
                        d_t: vec![G2Bytes([1; G2Bytes::SIZE])],
                        d_h: vec![G2Bytes([1; G2Bytes::SIZE])],
                        e: G2Bytes([1; G2Bytes::SIZE]),
                    };
                    1
                ],
            },
            pok: FsEncryptionPok {
                blinder: G1Bytes([1; G1Bytes::SIZE]),
                response: FrBytes([1; FrBytes::SIZE]),
            },
        },
    ));
    assert_eq!(
        "CspSecretKey::FsEncryption - REDACTED",
        format!("{:?}", cspsk_fs)
    );
}

#[test]
fn should_return_correct_enum_variant() {
    // Ed25519
    let key = CspSecretKey::Ed25519(ed25519_types::SecretKeyBytes(
        SecretArray::new_and_dont_zeroize_argument(&[0; ed25519_types::SecretKeyBytes::SIZE]),
    ));
    assert_eq!(key.enum_variant(), "Ed25519");

    // MultiBls12_381
    let key = CspSecretKey::MultiBls12_381(multi_types::SecretKeyBytes(
        [0; multi_types::SecretKeyBytes::SIZE],
    ));
    assert_eq!(key.enum_variant(), "MultiBls12_381");

    // ThresBls12_381
    let key = CspSecretKey::ThresBls12_381(threshold_types::SecretKeyBytes(
        [0; threshold_types::SecretKeyBytes::SIZE],
    ));
    assert_eq!(key.enum_variant(), "ThresBls12_381");

    // Secp256k1WithPublicKey
    let key = CspSecretKey::Secp256k1WithPublicKey(EphemeralKeySetBytes {
        secret_key_bytes: EphemeralSecretKeyBytes([0; EphemeralSecretKeyBytes::SIZE]),
        public_key_bytes: EphemeralPublicKeyBytes([0; EphemeralPublicKeyBytes::SIZE]),
        pop_bytes: EphemeralPopBytes([0; EphemeralPopBytes::SIZE]),
    });
    assert_eq!(key.enum_variant(), "Secp256k1WithPublicKey");

    // TlsEd25519
    let key = CspSecretKey::TlsEd25519(TlsEd25519SecretKeyDerBytes { bytes: vec![] });
    assert_eq!(key.enum_variant(), "TlsEd25519");

    // FsEncryption
    let key = CspSecretKey::FsEncryption(CspFsEncryptionKeySet::Groth20_Bls12_381(
        FsEncryptionKeySet {
            public_key: FsEncryptionPublicKey(G1Bytes([0; G1Bytes::SIZE])),
            secret_key: FsEncryptionSecretKey { bte_nodes: vec![] },
            pok: FsEncryptionPok {
                blinder: G1Bytes([0; G1Bytes::SIZE]),
                response: FrBytes([0; FrBytes::SIZE]),
            },
        },
    ));
    assert_eq!(key.enum_variant(), "FsEncryption");

    let mut rng = Seed::from_bytes(&[0u8; 32]).into_rng();
    let mega_private_key = MEGaPrivateKey::generate(EccCurveType::K256, &mut rng).unwrap();
    let mega_private_key_bytes = MEGaPrivateKeyK256Bytes::try_from(&mega_private_key).unwrap();
    let mega_public_key = mega_private_key.public_key().unwrap();
    let mega_public_key_bytes = MEGaPublicKeyK256Bytes::try_from(&mega_public_key).unwrap();
    let key = CspSecretKey::MEGaEncryptionK256(MEGaKeySetK256Bytes {
        public_key: mega_public_key_bytes,
        private_key: mega_private_key_bytes,
    });
    assert_eq!(key.enum_variant(), "MEGaEncryptionK256");

    let key = CspSecretKey::IDkgCommitmentOpening(CommitmentOpeningBytes::Simple(
        EccScalarBytes::K256([0u8; 32]),
    ));
    assert_eq!(key.enum_variant(), "IDkgCommitmentOpening");

    // plase add here tests for newly added ’CspSecretKey’ enums and increment the counter to match their count
    assert_eq!(CspSecretKey::COUNT, 8);
}

#[test]
fn should_return_correct_ed25519_pubkey_bytes_for_ed25519_pubkey() {
    let ed25519_csp_pk = CspPublicKey::ed25519_from_hex(TESTVEC_RFC8032_ED25519_SHA_ABC_PK);

    assert_eq!(
        ed25519_csp_pk.ed25519_bytes().unwrap().to_vec(),
        hex_to_byte_vec(TESTVEC_RFC8032_ED25519_SHA_ABC_PK)
    );
}

#[test]
fn should_return_no_ed25519_pubkey_bytes_for_non_ed25519_pubkey() {
    assert!(
        CspPublicKey::multi_bls12381_from_hex(TESTVEC_MULTI_BLS12_381_1_PK)
            .ed25519_bytes()
            .is_none()
    )
}

#[test]
fn should_return_correct_ed25519_signature_bytes_for_ed25519_signature() {
    let ed25519_csp_sig = CspSignature::ed25519_from_hex(TESTVEC_RFC8032_ED25519_SHA_ABC_SIG);

    assert_eq!(
        ed25519_csp_sig.ed25519_bytes().unwrap().to_vec(),
        hex_to_byte_vec(TESTVEC_RFC8032_ED25519_SHA_ABC_SIG)
    );
}

#[test]
fn should_return_no_ed25519_signature_bytes_for_non_ed25519_signature() {
    let signature = CspSignature::MultiBls12_381(MultiBls12_381_Signature::Individual(
        multi_types::IndividualSignatureBytes([0u8; multi_types::IndividualSignatureBytes::SIZE]),
    ));
    assert!(signature.ed25519_bytes().is_none())
}

#[test]
fn should_correctly_convert_basic_signature_to_ed25519_csp_signature() {
    let sig = BasicSigOf::<CryptoHashableTestDummy>::new(BasicSig(hex_to_byte_vec(
        TESTVEC_ED25519_STABILITY_1_SIG,
    )));

    let ed25519_csp_sig = SigConverter::for_target(AlgorithmId::Ed25519)
        .try_from_basic(&sig)
        .unwrap();

    assert_eq!(
        ed25519_csp_sig.ed25519_bytes().unwrap().to_vec(),
        hex_to_byte_vec(TESTVEC_ED25519_STABILITY_1_SIG)
    );
}

#[test]
fn should_correctly_convert_ed25519_csp_pubkey_to_user_public_key() {
    let ed25519_csp_pk = CspPublicKey::ed25519_from_hex(TESTVEC_RFC8032_ED25519_SHA_ABC_PK);

    let user_pk = UserPublicKey::try_from(ed25519_csp_pk).unwrap();

    assert_eq!(
        user_pk.key,
        hex_to_byte_vec(TESTVEC_RFC8032_ED25519_SHA_ABC_PK)
    );
}

#[test]
fn should_correctly_convert_ed25519_user_public_key_to_csp_public_key() {
    let user_pk = UserPublicKey {
        key: hex_to_byte_vec(TESTVEC_RFC8032_ED25519_SHA_ABC_PK),
        algorithm_id: AlgorithmId::Ed25519,
    };

    let ed25519_csp_pk = CspPublicKey::try_from(&user_pk).unwrap();

    assert_eq!(
        ed25519_csp_pk.ed25519_bytes().unwrap().to_vec(),
        hex_to_byte_vec(TESTVEC_RFC8032_ED25519_SHA_ABC_PK)
    );
}

#[test]
fn should_fail_to_convert_ed25519_user_pubkey_with_invalid_length_to_csp_pubkey() {
    let user_pk = UserPublicKey {
        key: vec![],
        algorithm_id: AlgorithmId::Ed25519,
    };

    let err = CspPublicKey::try_from(&user_pk).unwrap_err();

    assert!(err.is_malformed_public_key());
}

#[test]
fn should_correctly_compare_csp_signatures() {
    let ed25519_s1 = CspSignature::ed25519_from_hex(TESTVEC_RFC8032_ED25519_1_SIG);
    let ed25519_s1_2 = CspSignature::ed25519_from_hex(TESTVEC_RFC8032_ED25519_1_SIG);
    let ed25519_s2 = CspSignature::ed25519_from_hex(TESTVEC_RFC8032_ED25519_2_SIG);

    assert_eq!(ed25519_s1, ed25519_s1_2);
    assert_ne!(ed25519_s1, ed25519_s2);
}

#[test]
fn should_correctly_convert_ed25519_pk_proto_to_csp_public_key() {
    let pk_proto = PublicKeyProto {
        algorithm: AlgorithmIdProto::Ed25519 as i32,
        key_value: hex_to_byte_vec(TESTVEC_RFC8032_ED25519_SHA_ABC_PK),
        version: 0,
        proof_data: None,
    };
    let ed25519_csp_pk = CspPublicKey::try_from(pk_proto).unwrap();

    assert_eq!(
        ed25519_csp_pk.ed25519_bytes().unwrap().to_vec(),
        hex_to_byte_vec(TESTVEC_RFC8032_ED25519_SHA_ABC_PK)
    );
}

#[test]
fn should_correctly_convert_multi_bls12_381_pk_proto_to_csp_public_key() {
    let pk_proto = PublicKeyProto {
        algorithm: AlgorithmIdProto::MultiBls12381 as i32,
        key_value: hex_to_byte_vec(TESTVEC_MULTI_BLS12_381_1_PK),
        version: 0,
        proof_data: None,
    };
    let multi_bls_csp_pk = CspPublicKey::try_from(pk_proto).unwrap();

    assert_eq!(
        multi_bls_csp_pk.multi_bls12_381_bytes().unwrap().to_vec(),
        hex_to_byte_vec(TESTVEC_MULTI_BLS12_381_1_PK)
    );
}

#[test]
fn should_fail_conversion_to_csp_public_key_if_ed25519_pk_proto_is_too_short() {
    let pk_proto = PublicKeyProto {
        algorithm: AlgorithmIdProto::Ed25519 as i32,
        key_value: vec![0; ed25519_types::PublicKeyBytes::SIZE - 1],
        version: 0,
        proof_data: None,
    };
    let ed25519_csp_pk_result = CspPublicKey::try_from(pk_proto);
    assert!(ed25519_csp_pk_result.is_err());
    assert!(ed25519_csp_pk_result.unwrap_err().is_malformed_public_key());
}

#[test]
fn should_fail_conversion_to_csp_public_key_if_ed25519_pk_proto_is_too_long() {
    let pk_proto = PublicKeyProto {
        algorithm: AlgorithmIdProto::Ed25519 as i32,
        key_value: vec![0; ed25519_types::PublicKeyBytes::SIZE + 1],
        version: 0,
        proof_data: None,
    };
    let ed25519_csp_pk_result = CspPublicKey::try_from(pk_proto);
    assert!(ed25519_csp_pk_result.is_err());
    assert!(ed25519_csp_pk_result.unwrap_err().is_malformed_public_key());
}

#[test]
fn should_fail_conversion_to_csp_public_key_if_multi_bls12_381_pk_proto_is_too_short() {
    let pk_proto = PublicKeyProto {
        algorithm: AlgorithmIdProto::MultiBls12381 as i32,
        key_value: vec![0; multi_types::PublicKeyBytes::SIZE - 1],
        version: 0,
        proof_data: None,
    };
    let multi_csp_pk_result = CspPublicKey::try_from(pk_proto);
    assert!(multi_csp_pk_result.is_err());
    assert!(multi_csp_pk_result.unwrap_err().is_malformed_public_key());
}

#[test]
fn should_fail_conversion_to_csp_public_key_if_multi_bls12_381_pk_proto_is_too_long() {
    let pk_proto = PublicKeyProto {
        algorithm: AlgorithmIdProto::MultiBls12381 as i32,
        key_value: vec![0; multi_types::PublicKeyBytes::SIZE + 1],
        version: 0,
        proof_data: None,
    };
    let multi_csp_pk_result = CspPublicKey::try_from(pk_proto);
    assert!(multi_csp_pk_result.is_err());
    assert!(multi_csp_pk_result.unwrap_err().is_malformed_public_key());
}

#[test]
fn csp_signatures_should_have_a_nice_debug_representation() {
    let test_vectors = vec![
        (CspSignature::EcdsaP256(ecdsa_secp256r1_types::SignatureBytes([0u8; ecdsa_secp256r1_types::SignatureBytes::SIZE])), "CspSignature::EcdsaP256(\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==\")"),
        (CspSignature::EcdsaSecp256k1(ecdsa_secp256k1_types::SignatureBytes([0u8; ecdsa_secp256k1_types::SignatureBytes::SIZE])), "CspSignature::EcdsaSecp256k1(\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==\")"),
        (CspSignature::Ed25519(ed25519_types::SignatureBytes([0u8;ed25519_types::SignatureBytes::SIZE])), "CspSignature::Ed25519(SignatureBytes(\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==\"))"),
        (CspSignature::MultiBls12_381(MultiBls12_381_Signature::Individual(multi_types::IndividualSignatureBytes([0u8;multi_types::IndividualSignatureBytes::SIZE]))), "CspSignature::MultiBls12_381(Individual(\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\"))"),
        (CspSignature::MultiBls12_381(MultiBls12_381_Signature::Combined(multi_types::CombinedSignatureBytes([0u8;multi_types::CombinedSignatureBytes::SIZE]))), "CspSignature::MultiBls12_381(Combined(\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\"))"),
        (CspSignature::ThresBls12_381(ThresBls12_381_Signature::Individual(threshold_types::IndividualSignatureBytes([0u8;multi_types::IndividualSignatureBytes::SIZE]))), "CspSignature::ThresBls12_381(Individual(\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\"))"),
        (CspSignature::ThresBls12_381(ThresBls12_381_Signature::Combined(threshold_types::CombinedSignatureBytes([0u8;multi_types::CombinedSignatureBytes::SIZE]))), "CspSignature::ThresBls12_381(Combined(\"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\"))"),
        (CspSignature::RsaSha256(vec![1,2,3,4]), "CspSignature::RsaSha256(\"AQIDBA==\")")
    ];
    for (value, formatted) in test_vectors {
        assert_eq!(format!("{:?}", value), *formatted);
    }
}
